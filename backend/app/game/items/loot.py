import hashlib
import json
import random
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CharacterStatus,
    EventType,
    ItemInstanceMode,
    ItemLocationType,
    ItemOwnerType,
    ToolCapability,
)
from app.core.ids import generate_id
from app.db.models.character import Character
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.loot import (
    ActorLootProfile,
    CreatureHarvestResolution,
    LootResolution,
    LootTable,
    LootTableEntry,
)
from app.db.models.npc import NPC
from app.db.models.tool import ItemToolProfile
from app.game.attributes.service import get_character_attribute
from app.game.creatures.loot_catalog import (
    bestiary_item_key,
    ensure_bestiary_item_definitions,
)
from app.game.creatures.species import get as get_species
from app.game.items.service import create_item_instance, move_item_instance, set_item_owner
from app.game.items.tools import ToolError, validate_character_tool_use
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


@dataclass(frozen=True)
class HarvestResult:
    source_name: str
    method: str
    items: tuple[tuple[str, int], ...]
    luck_value: int
    replayed: bool = False

    @property
    def summary(self) -> str:
        label = _HARVEST_LABELS.get(self.method, self.method)
        if not self.items:
            return (
                f"Tenta {label} {self.source_name}, mas não obtém nenhum "
                "material aproveitável."
            )
        found = ", ".join(
            f"{quantity}× {name}" for name, quantity in self.items
        )
        return f"Conclui a coleta em {self.source_name} ({label}) e obtém: {found}."


_CUTTING_METHODS = {"esfolar", "butchering", "extrair"}
_HARVEST_LABELS = {
    "esfolar": "esfolar",
    "extrair": "extrair",
    "processar": "processar",
    "butchering": "cortar e preparar",
    "coletar": "coletar",
    "recolher": "recolher",
    "vasculhar": "vasculhar",
    "vasculhar ninho": "vasculhar o ninho",
    "depenar": "depenar",
    "capturar": "capturar",
    "filtrar": "filtrar",
    "tosquiar": "tosquiar",
}


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


def resolve_creature_harvest(
    db: Session,
    campaign_id: str,
    character: Character,
    target: str,
    method: str,
    *,
    action_key: str | None,
) -> HarvestResult:
    """Resolve each compatible dataset drop independently, once per method."""
    normalized_method = method.strip().casefold()
    if normalized_method not in _HARVEST_LABELS:
        raise LootError("Método de coleta desconhecido.")
    if action_key:
        previous = db.query(CreatureHarvestResolution).filter(
            CreatureHarvestResolution.action_key == action_key
        ).one_or_none()
        if previous is not None:
            if (
                previous.campaign_id != campaign_id
                or previous.character_id != character.id
            ):
                raise LootError("A chave desta ação pertence a outro personagem.")
            return HarvestResult(
                previous.source_name,
                previous.harvest_method,
                tuple(tuple(row) for row in json.loads(previous.result_json)),
                previous.luck_value,
                True,
            )
    if (
        character.campaign_id != campaign_id
        or character.status != CharacterStatus.ALIVE.value
    ):
        raise LootError("Somente o personagem vivo pode coletar neste mundo.")

    creature = _resolve_dead_creature(
        db, campaign_id, character.location_id, target
    )
    species = get_species(creature.creature_species)
    if species is None:
        raise LootError("A espécie desse corpo não existe no bestiário.")
    compatible = [drop for drop in species.loot if drop.method == normalized_method]
    if not compatible:
        available = sorted({drop.method for drop in species.loot})
        readable = ", ".join(
            _HARVEST_LABELS.get(value, value) for value in available
        )
        raise LootError(
            f"Esse corpo não permite esse método. Métodos possíveis: {readable}."
        )
    already = db.query(CreatureHarvestResolution).filter(
        CreatureHarvestResolution.campaign_id == campaign_id,
        CreatureHarvestResolution.source_npc_id == creature.id,
        CreatureHarvestResolution.harvest_method == normalized_method,
    ).one_or_none()
    if already is not None:
        raise LootError("Esse método já foi usado neste corpo.")
    if normalized_method in _CUTTING_METHODS:
        _require_cutting_tool(db, character)

    definitions = ensure_bestiary_item_definitions(db)
    luck = get_character_attribute(
        db, character.id, CharacterAttributeKey.LUCK
    ).value
    profile = json.loads(creature.profile_json or "{}")
    stage = species.stages.get(
        profile.get("stage"), species.stages.get("adulto")
    )
    loot_quantity = stage.loot_quantity if stage is not None else 1.0
    found: list[tuple[str, int]] = []
    for drop in compatible:
        rng = random.Random(
            _seed(campaign_id, creature.id, normalized_method, drop.item_id)
        )
        chance = effective_drop_chance(drop.chance_pct / 100.0, luck)
        if rng.random() >= chance:
            continue
        rolled = rng.randint(drop.quantity[0], drop.quantity[1])
        quantity = max(1, int(round(rolled * loot_quantity)))
        definition = definitions[bestiary_item_key(drop.item_id)]
        instance = create_item_instance(db, definition, quantity=quantity)
        move_item_instance(
            db,
            instance,
            location_type=ItemLocationType.CHARACTER,
            location_ref=character.id,
        )
        set_item_owner(
            db,
            instance,
            owner_type=ItemOwnerType.CHARACTER,
            owner_ref=character.id,
        )
        found.append((definition.name, quantity))
        from app.core.enums import ObjectiveTriggerType
        from app.game.quests.service import evaluate_objective_trigger

        evaluate_objective_trigger(
            db,
            campaign_id,
            character.id,
            ObjectiveTriggerType.RETRIEVE_ITEM,
            subject_id=f"definition:{definition.id}",
            amount=quantity,
        )

    resolved_key = action_key or generate_id("harvest_action")
    resolution = CreatureHarvestResolution(
        campaign_id=campaign_id,
        character_id=character.id,
        source_npc_id=creature.id,
        source_name=creature.name,
        species_key=species.key,
        harvest_method=normalized_method,
        action_key=resolved_key,
        luck_value=luck,
        result_json=json.dumps(found, ensure_ascii=False),
        created_world_minute=get_world_time(db, campaign_id).total_minutes(),
    )
    db.add(resolution)
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.LOOT_RESOLVED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "source_actor_type": "NPC",
            "source_actor_id": creature.id,
            "species_key": species.key,
            "harvest_method": normalized_method,
            "luck_value": luck,
            "items": found,
            "action_key": resolved_key,
        },
    )
    return HarvestResult(creature.name, normalized_method, tuple(found), luck)


def _require_cutting_tool(db: Session, character: Character) -> None:
    candidates = (
        db.query(ItemInstance)
        .join(
            ItemToolProfile,
            ItemToolProfile.item_id == ItemInstance.definition_id,
        )
        .filter(ItemInstance.campaign_id == character.campaign_id)
        .all()
    )
    for candidate in candidates:
        try:
            validate_character_tool_use(
                db,
                character.id,
                candidate.id,
                required_capability=ToolCapability.CUTTING,
            )
            return
        except ToolError:
            continue
    raise LootError(
        "Esse método exige uma ferramenta de corte acessível no inventário."
    )


def _resolve_dead_creature(
    db: Session,
    campaign_id: str,
    location_id: str | None,
    target: str,
) -> NPC:
    candidates = db.query(NPC).filter(
        NPC.campaign_id == campaign_id,
        NPC.alive.is_(False),
        NPC.creature_species.is_not(None),
        NPC.location_id == location_id,
    ).all()
    direct = db.get(NPC, target.strip())
    if direct in candidates:
        return direct
    normalized = target.strip().casefold()
    exact = [npc for npc in candidates if npc.name.casefold() == normalized]
    matches = exact or [
        npc
        for npc in candidates
        if normalized and normalized in npc.name.casefold()
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches and len(candidates) == 1:
        return candidates[0]
    raise LootError("Corpo de criatura não encontrado ou alvo ambíguo.")


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
