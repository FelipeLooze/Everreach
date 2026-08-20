import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, CombatDamageType, EquipmentSlot
from app.db.models.character import Character
from app.db.models.combat import CombatParticipant
from app.db.models.defense import ActorCombatDefense, ItemCombatProfile
from app.db.models.item import InventoryItem, Item
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer


MAX_SINGLE_ARMOR_RATING = 20
MAX_SINGLE_RESISTANCE = 20


class CombatDefenseError(ValueError):
    pass


@dataclass(frozen=True)
class DamageMitigation:
    damage_type: CombatDamageType
    armor: int
    resistance: int

    def apply(self, damage: int) -> int:
        return max(0, damage - self.armor - self.resistance)


def configure_item_combat_profile(
    db: Session,
    item: Item,
    *,
    slot: EquipmentSlot,
    armor_rating: int = 0,
    resistances: dict[CombatDamageType, int] | None = None,
) -> ItemCombatProfile:
    if db.get(Item, item.id) is None:
        raise CombatDefenseError("Item must be persisted before combat configuration.")
    if not isinstance(slot, EquipmentSlot):
        raise CombatDefenseError("Invalid equipment slot.")
    normalized_resistances = _validate_profile(armor_rating, resistances or {})
    values = {
        "slot": slot.value,
        "armor_rating": armor_rating,
        "resistances_json": _encode_resistances(normalized_resistances),
    }
    existing = db.get(ItemCombatProfile, item.id)
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in values.items()):
            raise CombatDefenseError("Item already has different combat mechanics.")
        return existing
    profile = ItemCombatProfile(item_id=item.id, **values)
    db.add(profile)
    db.flush()
    return profile


def configure_actor_combat_defense(
    db: Session,
    actor_type: CombatActorType,
    actor_id: str,
    *,
    armor_rating: int = 0,
    resistances: dict[CombatDamageType, int] | None = None,
) -> ActorCombatDefense:
    if not isinstance(actor_type, CombatActorType):
        raise CombatDefenseError("Invalid combat actor type.")
    normalized_id = actor_id.strip()
    if not normalized_id or _actor(db, actor_type, normalized_id) is None:
        raise CombatDefenseError("Combat defense actor does not exist.")
    normalized_resistances = _validate_profile(armor_rating, resistances or {})
    encoded = _encode_resistances(normalized_resistances)
    existing = (
        db.query(ActorCombatDefense)
        .filter(
            ActorCombatDefense.actor_type == actor_type.value,
            ActorCombatDefense.actor_id == normalized_id,
        )
        .one_or_none()
    )
    if existing is not None:
        if (
            existing.armor_rating != armor_rating
            or existing.resistances_json != encoded
        ):
            raise CombatDefenseError("Actor already has different combat defenses.")
        return existing
    profile = ActorCombatDefense(
        actor_type=actor_type.value,
        actor_id=normalized_id,
        armor_rating=armor_rating,
        resistances_json=encoded,
    )
    db.add(profile)
    db.flush()
    return profile


def equip_combat_item(db: Session, entry: InventoryItem) -> InventoryItem:
    if db.get(InventoryItem, entry.id) is None or entry.quantity < 1:
        raise CombatDefenseError("Inventory item must exist with positive quantity.")
    profile = db.get(ItemCombatProfile, entry.item_id)
    if profile is None:
        raise CombatDefenseError("Item has no authoritative combat profile.")
    conflict = (
        db.query(InventoryItem)
        .join(
            ItemCombatProfile,
            ItemCombatProfile.item_id == InventoryItem.item_id,
        )
        .filter(
            InventoryItem.character_id == entry.character_id,
            InventoryItem.id != entry.id,
            InventoryItem.equipped.is_(True),
            ItemCombatProfile.slot == profile.slot,
        )
        .first()
    )
    if conflict is not None:
        raise CombatDefenseError(f"Equipment slot {profile.slot} is already occupied.")
    entry.equipped = True
    db.flush()
    return entry


def unequip_combat_item(db: Session, entry: InventoryItem) -> InventoryItem:
    if db.get(InventoryItem, entry.id) is None:
        raise CombatDefenseError("Inventory item does not exist.")
    entry.equipped = False
    db.flush()
    return entry


def resolve_damage_mitigation(
    db: Session,
    participant: CombatParticipant,
    damage_type: CombatDamageType,
) -> DamageMitigation:
    if not isinstance(damage_type, CombatDamageType):
        raise CombatDefenseError("Invalid combat damage type.")
    innate = (
        db.query(ActorCombatDefense)
        .filter(
            ActorCombatDefense.actor_type == participant.actor_type,
            ActorCombatDefense.actor_id == participant.actor_id,
        )
        .one_or_none()
    )
    armor = innate.armor_rating if innate is not None else 0
    resistance = (
        _decode_resistances(innate.resistances_json).get(damage_type, 0)
        if innate is not None
        else 0
    )
    if participant.actor_type == CombatActorType.CHARACTER.value:
        equipped = (
            db.query(InventoryItem, ItemCombatProfile)
            .join(
                ItemCombatProfile,
                ItemCombatProfile.item_id == InventoryItem.item_id,
            )
            .filter(
                InventoryItem.character_id == participant.actor_id,
                InventoryItem.equipped.is_(True),
                InventoryItem.quantity > 0,
            )
            .all()
        )
        occupied_slots: set[str] = set()
        for _entry, profile in equipped:
            if profile.slot in occupied_slots:
                raise CombatDefenseError(
                    f"Character has multiple combat items equipped in {profile.slot}."
                )
            occupied_slots.add(profile.slot)
            armor += profile.armor_rating
            resistance += _decode_resistances(profile.resistances_json).get(
                damage_type,
                0,
            )
    return DamageMitigation(
        damage_type,
        armor if damage_type == CombatDamageType.PHYSICAL else 0,
        resistance,
    )


def _validate_profile(
    armor_rating: int,
    resistances: dict[CombatDamageType, int],
) -> dict[CombatDamageType, int]:
    if isinstance(armor_rating, bool) or not isinstance(armor_rating, int):
        raise CombatDefenseError("Armor rating must be an integer.")
    if not 0 <= armor_rating <= MAX_SINGLE_ARMOR_RATING:
        raise CombatDefenseError("Armor rating must be between 0 and 20.")
    normalized: dict[CombatDamageType, int] = {}
    for damage_type, value in resistances.items():
        if not isinstance(damage_type, CombatDamageType):
            raise CombatDefenseError("Invalid resistance damage type.")
        if isinstance(value, bool) or not isinstance(value, int):
            raise CombatDefenseError("Resistance must be an integer.")
        if not 0 <= value <= MAX_SINGLE_RESISTANCE:
            raise CombatDefenseError("Resistance must be between 0 and 20.")
        if value > 0:
            normalized[damage_type] = value
    return normalized


def _encode_resistances(resistances: dict[CombatDamageType, int]) -> str:
    return json.dumps(
        {key.value: value for key, value in sorted(resistances.items())},
        separators=(",", ":"),
    )


def _decode_resistances(value: str) -> dict[CombatDamageType, int]:
    try:
        raw = json.loads(value)
        return {CombatDamageType(key): int(amount) for key, amount in raw.items()}
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CombatDefenseError("Persisted combat resistance profile is invalid.") from exc


def _actor(
    db: Session,
    actor_type: CombatActorType,
    actor_id: str,
) -> Character | NPC | SimulatedPlayer | None:
    model = {
        CombatActorType.CHARACTER: Character,
        CombatActorType.NPC: NPC,
        CombatActorType.SIMULATED_PLAYER: SimulatedPlayer,
    }[actor_type]
    return db.get(model, actor_id)
