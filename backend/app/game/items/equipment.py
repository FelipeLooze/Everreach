import json

from sqlalchemy.orm import Session

from app.core.enums import (
    EquipmentSlot,
    EventType,
    ItemAccessibility,
    ItemLocationType,
    ItemType,
)
from app.db.models.equipment import ItemEquipmentProfile
from app.db.models.item import ItemDefinition, ItemInstance
from app.game.items.service import _set_item_location
from app.services.event_log import log_event


class EquipmentError(ValueError):
    pass


_BODY_SLOTS = {
    EquipmentSlot.HEAD,
    EquipmentSlot.TORSO,
    EquipmentSlot.LEGS,
    EquipmentSlot.FEET,
    EquipmentSlot.HANDS,
}
_HAND_AND_CARRY_SLOTS = {
    EquipmentSlot.MAIN_HAND,
    EquipmentSlot.OFF_HAND,
    EquipmentSlot.BOTH_HANDS,
    EquipmentSlot.BACK,
    EquipmentSlot.WAIST,
}
_CATEGORY_SLOTS: dict[ItemType, set[EquipmentSlot]] = {
    ItemType.ARMOR: _BODY_SLOTS | {EquipmentSlot.OFF_HAND, EquipmentSlot.BACK},
    ItemType.WEAPON: _HAND_AND_CARRY_SLOTS,
    ItemType.TOOL: _HAND_AND_CARRY_SLOTS,
    ItemType.CONTAINER: {EquipmentSlot.BACK, EquipmentSlot.WAIST},
    ItemType.AMMUNITION: {EquipmentSlot.BACK, EquipmentSlot.WAIST},
    ItemType.CONSUMABLE: {EquipmentSlot.WAIST},
    # Phase 9 created some combat definitions before item categories became
    # authoritative. MISC remains permissive solely for that legacy bridge.
    ItemType.MISC: set(EquipmentSlot),
}


def configure_item_equipment_profile(
    db: Session,
    item: ItemDefinition,
    *,
    allowed_slots: set[EquipmentSlot],
) -> ItemEquipmentProfile:
    if db.get(ItemDefinition, item.id) is None:
        raise EquipmentError("Item must be persisted before equipment configuration.")
    if not allowed_slots:
        raise EquipmentError("At least one equipment slot is required.")
    if any(not isinstance(slot, EquipmentSlot) for slot in allowed_slots):
        raise EquipmentError("Invalid equipment slot.")
    try:
        item_type = ItemType(item.type)
    except ValueError as exc:
        raise EquipmentError("Persisted item type is invalid.") from exc
    category_slots = _CATEGORY_SLOTS.get(item_type, set())
    invalid = allowed_slots - category_slots
    if invalid:
        raise EquipmentError(
            f"Item category {item_type.value} cannot use slots: "
            + ", ".join(sorted(slot.value for slot in invalid))
        )
    encoded = _encode_slots(allowed_slots)
    existing = db.get(ItemEquipmentProfile, item.id)
    if existing is not None:
        if existing.allowed_slots_json != encoded:
            raise EquipmentError(
                "Item already has different canonical equipment positions."
            )
        return existing
    profile = ItemEquipmentProfile(item_id=item.id, allowed_slots_json=encoded)
    db.add(profile)
    db.flush()
    return profile


def get_allowed_equipment_slots(
    profile: ItemEquipmentProfile,
) -> frozenset[EquipmentSlot]:
    try:
        raw = json.loads(profile.allowed_slots_json)
        if not isinstance(raw, list) or not raw:
            raise ValueError
        slots = frozenset(EquipmentSlot(value) for value in raw)
        if len(slots) != len(raw):
            raise ValueError
        return slots
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EquipmentError("Persisted equipment positions are invalid.") from exc


def equip_item(
    db: Session,
    instance: ItemInstance,
    *,
    slot: EquipmentSlot,
) -> ItemInstance:
    if db.get(ItemInstance, instance.id) is None:
        raise EquipmentError("Item instance does not exist.")
    if not isinstance(slot, EquipmentSlot):
        raise EquipmentError("Invalid equipment slot.")
    if instance.quantity != 1:
        raise EquipmentError("Only a single physical item can occupy equipment slots.")
    if instance.location_type not in {
        ItemLocationType.CHARACTER.value,
        ItemLocationType.CHARACTER_EQUIPPED.value,
    } or not instance.location_ref:
        raise EquipmentError("Item must be carried by a character before equipping.")
    if (
        instance.location_type == ItemLocationType.CHARACTER_EQUIPPED.value
        and instance.equipped_slot == slot.value
    ):
        return instance
    profile = db.get(ItemEquipmentProfile, instance.definition_id)
    if profile is None:
        raise EquipmentError("Item has no authoritative equipment profile.")
    if slot not in get_allowed_equipment_slots(profile):
        raise EquipmentError(f"Item cannot be equipped in {slot.value}.")
    equipped = (
        db.query(ItemInstance)
        .filter(
            ItemInstance.location_type == ItemLocationType.CHARACTER_EQUIPPED.value,
            ItemInstance.location_ref == instance.location_ref,
            ItemInstance.id != instance.id,
        )
        .all()
    )
    for other in equipped:
        other_slot = EquipmentSlot(other.equipped_slot)
        if equipment_slots_conflict(slot, other_slot):
            raise EquipmentError(f"Equipment slot {slot.value} is already occupied.")

    previous_slot = instance.equipped_slot
    _set_item_location(
        db,
        instance,
        location_type=ItemLocationType.CHARACTER_EQUIPPED,
        location_ref=instance.location_ref,
        equipped_slot=slot.value,
    )
    log_event(
        db,
        instance.campaign_id,
        EventType.ITEM_EQUIPPED,
        actor_type="character",
        actor_id=instance.location_ref,
        payload={
            "item_instance_id": instance.id,
            "definition_id": instance.definition_id,
            "previous_slot": previous_slot,
            "slot": slot.value,
            "accessibility": item_accessibility(instance).value,
        },
    )
    return instance


def unequip_item(db: Session, instance: ItemInstance) -> ItemInstance:
    if db.get(ItemInstance, instance.id) is None:
        raise EquipmentError("Item instance does not exist.")
    if (
        instance.location_type != ItemLocationType.CHARACTER_EQUIPPED.value
        or not instance.location_ref
        or not instance.equipped_slot
    ):
        raise EquipmentError("Item is not equipped by a character.")
    character_id = instance.location_ref
    previous_slot = instance.equipped_slot
    _set_item_location(
        db,
        instance,
        location_type=ItemLocationType.CHARACTER,
        location_ref=character_id,
        equipped_slot=None,
    )
    log_event(
        db,
        instance.campaign_id,
        EventType.ITEM_UNEQUIPPED,
        actor_type="character",
        actor_id=character_id,
        payload={
            "item_instance_id": instance.id,
            "definition_id": instance.definition_id,
            "previous_slot": previous_slot,
            "accessibility": item_accessibility(instance).value,
        },
    )
    return instance


def item_accessibility(instance: ItemInstance) -> ItemAccessibility:
    if instance.location_type != ItemLocationType.CHARACTER_EQUIPPED.value:
        return ItemAccessibility.STOWED
    try:
        slot = EquipmentSlot(instance.equipped_slot)
    except (TypeError, ValueError) as exc:
        raise EquipmentError("Equipped item has an invalid physical slot.") from exc
    if slot in {
        EquipmentSlot.MAIN_HAND,
        EquipmentSlot.OFF_HAND,
        EquipmentSlot.BOTH_HANDS,
    }:
        return ItemAccessibility.IMMEDIATE
    if slot == EquipmentSlot.WAIST:
        return ItemAccessibility.QUICK
    if slot == EquipmentSlot.BACK:
        return ItemAccessibility.STOWED
    return ItemAccessibility.WORN


def resolve_item_accessibility(
    db: Session,
    instance: ItemInstance,
) -> ItemAccessibility:
    """Resolve accessibility through the physical container hierarchy."""
    if instance.location_type != ItemLocationType.CONTAINER.value:
        return item_accessibility(instance)
    current = instance
    depth = 0
    visited: set[str] = set()
    while current.location_type == ItemLocationType.CONTAINER.value:
        if current.id in visited or not current.location_ref:
            raise EquipmentError("Invalid recursive container hierarchy.")
        visited.add(current.id)
        parent = db.get(ItemInstance, current.location_ref)
        if parent is None:
            raise EquipmentError("Container hierarchy references a missing item.")
        current = parent
        depth += 1
    if depth == 1 and item_accessibility(current) == ItemAccessibility.QUICK:
        return ItemAccessibility.QUICK
    return ItemAccessibility.STOWED


def equipment_slots_conflict(first: EquipmentSlot, second: EquipmentSlot) -> bool:
    if first == second:
        return True
    hand_slots = {
        EquipmentSlot.MAIN_HAND,
        EquipmentSlot.OFF_HAND,
        EquipmentSlot.BOTH_HANDS,
    }
    return (
        EquipmentSlot.BOTH_HANDS in {first, second}
        and first in hand_slots
        and second in hand_slots
    )


def _encode_slots(slots: set[EquipmentSlot]) -> str:
    return json.dumps(
        sorted(slot.value for slot in slots),
        separators=(",", ":"),
    )
