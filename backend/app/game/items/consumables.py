import json
from dataclasses import dataclass
from math import isfinite

from sqlalchemy.orm import Session

from app.core.enums import CharacterStatus, EventType, ItemAccessibility, ItemType
from app.core.ids import generate_id
from app.db.models.character import Character
from app.db.models.consumable import ItemConsumableProfile, ItemConsumptionRecord
from app.db.models.item import ItemDefinition, ItemInstance
from app.game.items.containers import is_item_possessed_by_character
from app.game.items.equipment import resolve_item_accessibility
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


class ConsumableError(ValueError):
    pass


@dataclass(frozen=True)
class ConsumptionResult:
    item_name: str
    effects: dict[str, float]
    use_minutes: int
    replayed: bool = False

    @property
    def summary(self) -> str:
        labels = {"hp": "HP", "mana": "Mana", "stamina": "Stamina", "hunger": "Fome", "thirst": "Sede"}
        changes = ", ".join(f"{labels[key]} +{value:g}" for key, value in self.effects.items() if value > 0)
        return f"Usa {self.item_name}. {changes}." if changes else f"Usa {self.item_name}."


def configure_consumable_profile(
    db: Session,
    definition: ItemDefinition,
    *,
    hp_restore: float = 0,
    mana_restore: float = 0,
    stamina_restore: float = 0,
    hunger_restore: float = 0,
    thirst_restore: float = 0,
    use_minutes: int = 1,
) -> ItemConsumableProfile:
    if definition.type != ItemType.CONSUMABLE.value:
        raise ConsumableError("Only CONSUMABLE definitions may receive a consumable profile.")
    values = (hp_restore, mana_restore, stamina_restore, hunger_restore, thirst_restore)
    if any(isinstance(value, bool) or not isfinite(value) or value < 0 for value in values):
        raise ConsumableError("Consumable restoration values must be finite and non-negative.")
    if not any(value > 0 for value in values):
        raise ConsumableError("A consumable must have at least one real effect.")
    if isinstance(use_minutes, bool) or not isinstance(use_minutes, int) or use_minutes < 0:
        raise ConsumableError("Consumable use time must be a non-negative integer.")
    profile = db.get(ItemConsumableProfile, definition.id)
    payload = dict(
        hp_restore=float(hp_restore), mana_restore=float(mana_restore),
        stamina_restore=float(stamina_restore), hunger_restore=float(hunger_restore),
        thirst_restore=float(thirst_restore), use_minutes=use_minutes,
    )
    if profile is None:
        profile = ItemConsumableProfile(item_definition_id=definition.id, **payload)
        db.add(profile)
    else:
        for key, value in payload.items():
            setattr(profile, key, value)
    db.flush()
    return profile


def use_consumable(
    db: Session,
    campaign_id: str,
    character: Character,
    target: str,
    *,
    action_key: str | None,
    in_combat: bool = False,
) -> ConsumptionResult:
    if action_key:
        previous = db.query(ItemConsumptionRecord).filter(ItemConsumptionRecord.action_key == action_key).one_or_none()
        if previous is not None:
            if previous.campaign_id != campaign_id or previous.character_id != character.id:
                raise ConsumableError("Action key belongs to another actor or campaign.")
            definition = db.get(ItemDefinition, previous.item_definition_id)
            return ConsumptionResult(definition.name, json.loads(previous.effects_json), 0, replayed=True)
    if character.campaign_id != campaign_id or character.status != CharacterStatus.ALIVE.value:
        raise ConsumableError("Only the living character may use a consumable from this campaign.")
    item = _resolve_possessed_item(db, campaign_id, character.id, target)
    if in_combat and resolve_item_accessibility(db, item) not in {
        ItemAccessibility.IMMEDIATE,
        ItemAccessibility.QUICK,
    }:
        raise ConsumableError("The consumable is stowed and not accessible during combat.")
    definition = db.get(ItemDefinition, item.definition_id)
    profile = db.get(ItemConsumableProfile, definition.id)
    if profile is None:
        raise ConsumableError("This item has no authoritative consumable effect.")

    before = _resources(character)
    character.hp_current = min(character.hp_max, character.hp_current + profile.hp_restore)
    character.mana_current = min(character.mana_max, character.mana_current + profile.mana_restore)
    character.stamina_current = min(character.stamina_max, character.stamina_current + profile.stamina_restore)
    character.hunger_current = min(character.hunger_max, character.hunger_current + profile.hunger_restore)
    character.thirst_current = min(character.thirst_max, character.thirst_current + profile.thirst_restore)
    after = _resources(character)
    effects = {key: round(after[key] - before[key], 3) for key in before}
    if not any(value > 0 for value in effects.values()):
        raise ConsumableError("The consumable would have no effect right now.")

    instance_id = item.id
    if item.quantity > 1:
        item.quantity -= 1
    else:
        db.delete(item)
    resolved_key = action_key or generate_id("consume_action")
    record = ItemConsumptionRecord(
        id=generate_id("consumption"), campaign_id=campaign_id,
        character_id=character.id, action_key=resolved_key,
        item_instance_id=instance_id, item_definition_id=definition.id,
        effects_json=json.dumps(effects, sort_keys=True),
        created_world_minute=get_world_time(db, campaign_id).total_minutes(),
    )
    db.add(record)
    db.flush()
    log_event(
        db, campaign_id, EventType.ITEM_CONSUMED,
        actor_type="character", actor_id=character.id,
        payload={"item_instance_id": instance_id, "item_definition_id": definition.id, "effects": effects, "action_key": resolved_key},
    )
    return ConsumptionResult(definition.name, effects, profile.use_minutes)


def _resources(character: Character) -> dict[str, float]:
    return {"hp": character.hp_current, "mana": character.mana_current, "stamina": character.stamina_current, "hunger": character.hunger_current, "thirst": character.thirst_current}


def _resolve_possessed_item(db: Session, campaign_id: str, character_id: str, target: str) -> ItemInstance:
    direct = db.get(ItemInstance, target.strip())
    candidates = [direct] if direct is not None else (
        db.query(ItemInstance).join(ItemDefinition).filter(ItemInstance.campaign_id == campaign_id).all()
    )
    candidates = [item for item in candidates if item is not None and is_item_possessed_by_character(db, item, character_id)]
    if direct is None:
        normalized = target.strip().casefold()
        exact = [item for item in candidates if item.definition.name.casefold() == normalized]
        candidates = exact or [item for item in candidates if normalized in item.definition.name.casefold()]
    if len(candidates) != 1:
        raise ConsumableError("Consumable not found or target is ambiguous.")
    return candidates[0]
