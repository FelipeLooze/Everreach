import hashlib
import json
import random
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import CharacterAttributeKey, CharacterStatus, EventType, ItemInstanceMode, ItemLocationType, ItemOwnerType
from app.core.ids import generate_id
from app.db.models.character import Character
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.loot import ActorLootProfile, LootResolution, LootTable, LootTableEntry
from app.db.models.npc import NPC
from app.game.attributes.service import get_character_attribute
from app.game.items.service import create_item_instance, move_item_instance, set_item_owner
from app.game.npcs.service import effective_npc_location_id
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


class LootError(ValueError):
    pass


@dataclass(frozen=True)
class LootResult:
    source_name: str
    items: tuple[tuple[str, int], ...]
    luck_value: int
    replayed: bool = False

    @property
    def summary(self) -> str:
        if not self.items:
            return f"Revista {self.source_name}, mas não encontra nada que possa levar."
        found = ", ".join(f"{quantity}× {name}" for name, quantity in self.items)
        return f"Saqueia {self.source_name} e obtém: {found}."


def effective_drop_chance(base_chance: float, luck_value: int) -> float:
    """Luck improves only optional loot, by one percentage point per point
    above the baseline. It cannot create guaranteed drops above 100%."""
    return min(1.0, base_chance + max(0, luck_value - 10) * 0.01)


def create_loot_table(db: Session, key: str, name: str) -> LootTable:
    normalized = key.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]+", normalized) or not name.strip():
        raise LootError("Loot table requires a stable key and name.")
    existing = db.query(LootTable).filter(LootTable.key == normalized).one_or_none()
    if existing is not None:
        return existing
    table = LootTable(key=normalized, name=name.strip())
    db.add(table); db.flush()
    return table


def add_loot_entry(db: Session, table: LootTable, definition: ItemDefinition, *, drop_chance: float, min_quantity: int = 1, max_quantity: int = 1) -> LootTableEntry:
    if isinstance(drop_chance, bool) or not 0 <= drop_chance <= 1:
        raise LootError("Drop chance must be between zero and one.")
    if min_quantity <= 0 or max_quantity < min_quantity:
        raise LootError("Invalid loot quantity range.")
    entry = LootTableEntry(loot_table_id=table.id, item_definition_id=definition.id, drop_chance=float(drop_chance), min_quantity=min_quantity, max_quantity=max_quantity)
    db.add(entry); db.flush()
    return entry


def assign_npc_loot_table(db: Session, npc: NPC, table: LootTable) -> ActorLootProfile:
    profile = ActorLootProfile(campaign_id=npc.campaign_id, actor_type="NPC", actor_id=npc.id, loot_table_id=table.id)
    db.add(profile); db.flush()
    return profile


def resolve_npc_loot(db: Session, campaign_id: str, character: Character, target: str, *, action_key: str | None) -> LootResult:
    if action_key:
        previous = db.query(LootResolution).filter(LootResolution.action_key == action_key).one_or_none()
        if previous is not None:
            if previous.campaign_id != campaign_id or previous.character_id != character.id:
                raise LootError("Action key belongs to another actor or campaign.")
            npc = db.get(NPC, previous.source_actor_id)
            return LootResult(npc.name if npc else "o alvo", tuple(tuple(row) for row in json.loads(previous.result_json)), previous.luck_value, True)
    if character.campaign_id != campaign_id or character.status != CharacterStatus.ALIVE.value:
        raise LootError("Only the living character may loot in this campaign.")
    npc = _resolve_dead_npc(db, campaign_id, character.location_id, target)
    if npc.alive:
        raise LootError("A living actor cannot be looted.")
    already = db.query(LootResolution).filter(LootResolution.campaign_id == campaign_id, LootResolution.source_actor_type == "NPC", LootResolution.source_actor_id == npc.id).one_or_none()
    if already is not None:
        raise LootError("This target has already been looted.")
    luck = get_character_attribute(db, character.id, CharacterAttributeKey.LUCK).value
    found: list[tuple[str, int]] = []

    carried = db.query(ItemInstance).filter(ItemInstance.campaign_id == campaign_id, ItemInstance.location_type == ItemLocationType.NPC.value, ItemInstance.location_ref == npc.id).all()
    for item in carried:
        definition = db.get(ItemDefinition, item.definition_id)
        move_item_instance(db, item, location_type=ItemLocationType.CHARACTER, location_ref=character.id)
        set_item_owner(db, item, owner_type=ItemOwnerType.CHARACTER, owner_ref=character.id)
        found.append((definition.name, item.quantity))

    profile = db.query(ActorLootProfile).filter(ActorLootProfile.campaign_id == campaign_id, ActorLootProfile.actor_type == "NPC", ActorLootProfile.actor_id == npc.id).one_or_none()
    if profile is not None:
        entries = db.query(LootTableEntry).filter(LootTableEntry.loot_table_id == profile.loot_table_id).order_by(LootTableEntry.id).all()
        for entry in entries:
            rng = random.Random(_seed(campaign_id, npc.id, entry.id))
            effective_chance = effective_drop_chance(entry.drop_chance, luck)
            if rng.random() >= effective_chance:
                continue
            definition = db.get(ItemDefinition, entry.item_definition_id)
            quantity = rng.randint(entry.min_quantity, entry.max_quantity)
            if definition.instance_mode == ItemInstanceMode.UNIQUE.value:
                for _ in range(quantity):
                    _grant(db, definition, character)
            else:
                instance = create_item_instance(db, definition, quantity=quantity)
                move_item_instance(db, instance, location_type=ItemLocationType.CHARACTER, location_ref=character.id)
                set_item_owner(db, instance, owner_type=ItemOwnerType.CHARACTER, owner_ref=character.id)
            found.append((definition.name, quantity))

    resolved_key = action_key or generate_id("loot_action")
    resolution = LootResolution(campaign_id=campaign_id, character_id=character.id, source_actor_type="NPC", source_actor_id=npc.id, action_key=resolved_key, luck_value=luck, result_json=json.dumps(found, ensure_ascii=False), created_world_minute=get_world_time(db, campaign_id).total_minutes())
    db.add(resolution); db.flush()
    log_event(db, campaign_id, EventType.LOOT_RESOLVED, actor_type="character", actor_id=character.id, payload={"source_actor_type": "NPC", "source_actor_id": npc.id, "luck_value": luck, "items": found, "action_key": resolved_key})
    return LootResult(npc.name, tuple(found), luck)


def _grant(db: Session, definition: ItemDefinition, character: Character) -> None:
    instance = create_item_instance(db, definition)
    move_item_instance(db, instance, location_type=ItemLocationType.CHARACTER, location_ref=character.id)
    set_item_owner(db, instance, owner_type=ItemOwnerType.CHARACTER, owner_ref=character.id)


def _resolve_dead_npc(db: Session, campaign_id: str, location_id: str | None, target: str) -> NPC:
    db.flush()
    candidates = db.query(NPC).filter(
        NPC.campaign_id == campaign_id, NPC.alive.is_(False)
    ).all()
    candidates = [npc for npc in candidates if effective_npc_location_id(npc) == location_id]
    direct = db.get(NPC, target.strip())
    if direct in candidates:
        return direct
    normalized = target.strip().casefold()
    exact = [npc for npc in candidates if npc.name.casefold() == normalized]
    matches = exact or [npc for npc in candidates if normalized in npc.name.casefold()]
    if len(matches) != 1:
        raise LootError("Dead loot source not found or target is ambiguous.")
    return matches[0]


def _seed(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256("|".join(parts).encode()).digest()[:8], "big")
