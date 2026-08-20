import json

from sqlalchemy.orm import Session

from app.core.enums import BodyArea, EquipmentSlot, ItemType, PhysicalDamageProfile
from app.db.models.defense import ItemArmorProfile
from app.db.models.equipment import ItemEquipmentProfile
from app.db.models.item import ItemDefinition
from app.game.items.equipment import EquipmentError, get_allowed_equipment_slots


MAX_SINGLE_PHYSICAL_PROTECTION = 20


class ArmorError(ValueError):
    pass


def configure_item_armor_profile(
    db: Session,
    item: ItemDefinition,
    *,
    coverage: set[BodyArea],
    physical_protections: dict[PhysicalDamageProfile, int],
) -> ItemArmorProfile:
    if db.get(ItemDefinition, item.id) is None:
        raise ArmorError("Armor item must be persisted before configuration.")
    if item.type != ItemType.ARMOR.value:
        raise ArmorError("Only ARMOR item definitions can have an armor profile.")
    if not coverage or any(not isinstance(area, BodyArea) for area in coverage):
        raise ArmorError("At least one valid body coverage area is required.")
    normalized = _validate_protections(physical_protections)
    equipment = db.get(ItemEquipmentProfile, item.id)
    if equipment is None:
        raise ArmorError("Armor requires an equipment profile first.")
    try:
        slots = get_allowed_equipment_slots(equipment)
    except EquipmentError as exc:
        raise ArmorError(str(exc)) from exc
    worn_areas = {
        BodyArea(slot.value)
        for slot in slots
        if slot.value in {area.value for area in BodyArea if area != BodyArea.ARMS}
    }
    if not worn_areas or not (coverage & worn_areas):
        raise ArmorError("Armor coverage must include one of its wearable body positions.")

    values = {
        "coverage_json": _encode_coverage(coverage),
        "physical_protections_json": _encode_protections(normalized),
    }
    existing = db.get(ItemArmorProfile, item.id)
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in values.items()):
            raise ArmorError("Item already has different canonical armor mechanics.")
        return existing
    profile = ItemArmorProfile(item_id=item.id, **values)
    db.add(profile)
    db.flush()
    return profile


def get_armor_coverage(profile: ItemArmorProfile) -> frozenset[BodyArea]:
    try:
        raw = json.loads(profile.coverage_json)
        if not isinstance(raw, list) or not raw:
            raise ValueError
        result = frozenset(BodyArea(value) for value in raw)
        if len(result) != len(raw):
            raise ValueError
        return result
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ArmorError("Persisted armor coverage is invalid.") from exc


def get_armor_physical_protections(
    profile: ItemArmorProfile,
) -> dict[PhysicalDamageProfile, int]:
    try:
        raw = json.loads(profile.physical_protections_json)
        if not isinstance(raw, dict):
            raise ValueError
        return _validate_protections(
            {PhysicalDamageProfile(key): value for key, value in raw.items()}
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ArmorError("Persisted armor physical protections are invalid.") from exc


def _validate_protections(
    protections: dict[PhysicalDamageProfile, int],
) -> dict[PhysicalDamageProfile, int]:
    if not protections:
        raise ArmorError("At least one physical protection is required.")
    normalized: dict[PhysicalDamageProfile, int] = {}
    for profile, value in protections.items():
        if not isinstance(profile, PhysicalDamageProfile):
            raise ArmorError("Invalid physical protection profile.")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ArmorError("Physical protection must be an integer.")
        if not 0 <= value <= MAX_SINGLE_PHYSICAL_PROTECTION:
            raise ArmorError("Physical protection must be between 0 and 20.")
        if value > 0:
            normalized[profile] = value
    if not normalized:
        raise ArmorError("Armor must provide at least one positive physical protection.")
    return normalized


def _encode_coverage(coverage: set[BodyArea]) -> str:
    return json.dumps(sorted(area.value for area in coverage), separators=(",", ":"))


def _encode_protections(protections: dict[PhysicalDamageProfile, int]) -> str:
    return json.dumps(
        {key.value: protections[key] for key in sorted(protections, key=lambda key: key.value)},
        separators=(",", ":"),
    )
