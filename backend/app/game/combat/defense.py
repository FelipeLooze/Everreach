import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    BodyArea,
    CombatActorType,
    CombatDamageType,
    EquipmentSlot,
    ItemAccessibility,
    ItemLocationType,
    PhysicalDamageProfile,
)
from app.db.models.character import Character
from app.db.models.combat import CombatParticipant
from app.db.models.defense import ActorCombatDefense, ItemArmorProfile, ItemCombatProfile
from app.db.models.equipment import ItemEquipmentProfile
from app.db.models.item import Item, ItemInstance
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.items.armor import get_armor_coverage, get_armor_physical_protections
from app.game.items.equipment import (
    EquipmentError,
    configure_item_equipment_profile,
    equipment_slots_conflict,
    equip_item,
    get_allowed_equipment_slots,
    item_accessibility,
    unequip_item,
)


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
        _ensure_combat_equipment_position(db, item, slot)
        return existing
    profile = ItemCombatProfile(item_id=item.id, **values)
    _ensure_combat_equipment_position(db, item, slot)
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


def equip_combat_item(db: Session, entry: ItemInstance) -> ItemInstance:
    if db.get(ItemInstance, entry.id) is None or entry.quantity < 1:
        raise CombatDefenseError("Inventory item must exist with positive quantity.")
    if (
        entry.location_type != ItemLocationType.CHARACTER.value
        or not entry.location_ref
    ):
        raise CombatDefenseError("Item must be carried by a character before equipping.")
    profile = db.get(ItemCombatProfile, entry.definition_id)
    if profile is None:
        raise CombatDefenseError("Item has no authoritative combat profile.")
    try:
        return equip_item(db, entry, slot=EquipmentSlot(profile.slot))
    except (EquipmentError, ValueError) as exc:
        raise CombatDefenseError(str(exc)) from exc


def unequip_combat_item(db: Session, entry: ItemInstance) -> ItemInstance:
    if db.get(ItemInstance, entry.id) is None:
        raise CombatDefenseError("Inventory item does not exist.")
    if entry.location_type != ItemLocationType.CHARACTER_EQUIPPED.value:
        raise CombatDefenseError("Item is not equipped by a character.")
    try:
        return unequip_item(db, entry)
    except EquipmentError as exc:
        raise CombatDefenseError(str(exc)) from exc


def resolve_damage_mitigation(
    db: Session,
    participant: CombatParticipant,
    damage_type: CombatDamageType,
    *,
    physical_damage_profile: PhysicalDamageProfile | None = None,
    target_body_area: BodyArea | None = None,
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
    if damage_type == CombatDamageType.PHYSICAL and (
        (physical_damage_profile is None) != (target_body_area is None)
    ):
        raise CombatDefenseError(
            "Physical profile and target body area must be provided together."
        )
    if participant.actor_type == CombatActorType.CHARACTER.value:
        equipped = (
            db.query(ItemInstance, ItemCombatProfile)
            .join(
                ItemCombatProfile,
                ItemCombatProfile.item_id == ItemInstance.definition_id,
            )
            .filter(
                ItemInstance.location_ref == participant.actor_id,
                ItemInstance.location_type == ItemLocationType.CHARACTER_EQUIPPED.value,
                ItemInstance.quantity > 0,
            )
            .all()
        )
        occupied_slots: set[EquipmentSlot] = set()
        for entry, profile in equipped:
            if not entry.equipped_slot:
                raise CombatDefenseError("Equipped combat item has no physical slot.")
            try:
                physical_slot = EquipmentSlot(entry.equipped_slot)
            except ValueError as exc:
                raise CombatDefenseError(
                    "Equipped combat item has an invalid physical slot."
                ) from exc
            if any(
                equipment_slots_conflict(physical_slot, occupied)
                for occupied in occupied_slots
            ):
                raise CombatDefenseError(
                    f"Character has conflicting equipment in {entry.equipped_slot}."
                )
            occupied_slots.add(physical_slot)
            armor_profile = db.get(ItemArmorProfile, entry.definition_id)
            if physical_damage_profile is None:
                # Compatibility for actions recorded before Phase 10F.
                armor += profile.armor_rating
            elif armor_profile is None:
                armor += profile.armor_rating
            elif (
                item_accessibility(entry) == ItemAccessibility.WORN
                and target_body_area in get_armor_coverage(armor_profile)
            ):
                armor += get_armor_physical_protections(armor_profile).get(
                    physical_damage_profile, 0
                )
            resistance += _decode_resistances(profile.resistances_json).get(
                damage_type,
                0,
            )
        if physical_damage_profile is not None:
            profiled_armor = (
                db.query(ItemInstance, ItemArmorProfile)
                .join(
                    ItemArmorProfile,
                    ItemArmorProfile.item_id == ItemInstance.definition_id,
                )
                .outerjoin(
                    ItemCombatProfile,
                    ItemCombatProfile.item_id == ItemArmorProfile.item_id,
                )
                .filter(
                    ItemInstance.location_ref == participant.actor_id,
                    ItemInstance.location_type == ItemLocationType.CHARACTER_EQUIPPED.value,
                    ItemInstance.quantity > 0,
                    ItemCombatProfile.item_id.is_(None),
                )
                .all()
            )
            for entry, profile in profiled_armor:
                if (
                    item_accessibility(entry) == ItemAccessibility.WORN
                    and target_body_area in get_armor_coverage(profile)
                ):
                    armor += get_armor_physical_protections(profile).get(
                        physical_damage_profile, 0
                    )
    return DamageMitigation(
        damage_type,
        armor if damage_type == CombatDamageType.PHYSICAL else 0,
        resistance,
    )


def _ensure_combat_equipment_position(
    db: Session,
    item: Item,
    slot: EquipmentSlot,
) -> None:
    equipment_profile = db.get(ItemEquipmentProfile, item.id)
    if equipment_profile is None:
        try:
            configure_item_equipment_profile(db, item, allowed_slots={slot})
        except EquipmentError as exc:
            raise CombatDefenseError(str(exc)) from exc
        return
    try:
        allowed_slots = get_allowed_equipment_slots(equipment_profile)
    except EquipmentError as exc:
        raise CombatDefenseError(str(exc)) from exc
    if slot not in allowed_slots:
        raise CombatDefenseError(
            "Combat profile slot is not an allowed physical equipment position."
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
