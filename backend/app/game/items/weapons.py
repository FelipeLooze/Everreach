import json
import random
from dataclasses import replace

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActionType,
    CombatActorType,
    CombatRangeBand,
    EquipmentSlot,
    ItemAccessibility,
    ItemLocationType,
    ItemType,
    PhysicalDamageProfile,
    WeaponFamily,
    WeaponHandRequirement,
    WeaponReach,
)
from app.db.models.combat import CombatAction, CombatEncounter, CombatParticipant
from app.db.models.equipment import ItemEquipmentProfile
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.weapon import ItemWeaponProfile
from app.game.combat.actions import (
    CombatActionError,
    CombatActionResolution,
    basic_attack_mechanics,
    resolve_profiled_attack,
)
from app.game.items.equipment import (
    EquipmentError,
    get_allowed_equipment_slots,
    item_accessibility,
)


class WeaponError(ValueError):
    pass


def configure_item_weapon_profile(
    db: Session,
    item: ItemDefinition,
    *,
    weapon_family: WeaponFamily,
    damage_profiles: set[PhysicalDamageProfile],
    reach: WeaponReach,
    hand_requirement: WeaponHandRequirement,
) -> ItemWeaponProfile:
    if db.get(ItemDefinition, item.id) is None:
        raise WeaponError("Weapon item must be persisted before configuration.")
    if item.type != ItemType.WEAPON.value:
        raise WeaponError("Only WEAPON item definitions can have a weapon profile.")
    if not isinstance(weapon_family, WeaponFamily):
        raise WeaponError("Invalid weapon family.")
    if not damage_profiles or any(
        not isinstance(profile, PhysicalDamageProfile)
        for profile in damage_profiles
    ):
        raise WeaponError("At least one valid physical damage profile is required.")
    if not isinstance(reach, WeaponReach):
        raise WeaponError("Invalid weapon reach.")
    if not isinstance(hand_requirement, WeaponHandRequirement):
        raise WeaponError("Invalid weapon hand requirement.")
    equipment_profile = db.get(ItemEquipmentProfile, item.id)
    if equipment_profile is None:
        raise WeaponError("Weapon requires an equipment profile first.")
    try:
        allowed_slots = get_allowed_equipment_slots(equipment_profile)
    except EquipmentError as exc:
        raise WeaponError(str(exc)) from exc
    _validate_hand_positions(hand_requirement, allowed_slots)

    values = {
        "weapon_family": weapon_family.value,
        "damage_profiles_json": _encode_damage_profiles(damage_profiles),
        "reach": reach.value,
        "hand_requirement": hand_requirement.value,
    }
    existing = db.get(ItemWeaponProfile, item.id)
    if existing is not None:
        if any(getattr(existing, key) != value for key, value in values.items()):
            raise WeaponError("Item already has different canonical weapon mechanics.")
        return existing
    profile = ItemWeaponProfile(item_id=item.id, **values)
    db.add(profile)
    db.flush()
    return profile


def get_weapon_damage_profiles(
    profile: ItemWeaponProfile,
) -> frozenset[PhysicalDamageProfile]:
    try:
        raw = json.loads(profile.damage_profiles_json)
        if not isinstance(raw, list) or not raw:
            raise ValueError
        profiles = frozenset(PhysicalDamageProfile(value) for value in raw)
        if len(profiles) != len(raw):
            raise ValueError
        return profiles
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WeaponError("Persisted weapon damage profiles are invalid.") from exc


def resolve_weapon_attack(
    db: Session,
    encounter: CombatEncounter,
    actor: CombatParticipant,
    target: CombatParticipant,
    *,
    weapon_instance_id: str,
    action_type: CombatActionType,
    damage_profile: PhysicalDamageProfile,
    action_key: str,
    rng: random.Random | None = None,
) -> CombatActionResolution:
    if actor.actor_type != CombatActorType.CHARACTER.value:
        raise WeaponError("Only a character can use character equipment.")
    if not isinstance(action_type, CombatActionType):
        raise WeaponError("Invalid weapon attack type.")
    if not isinstance(damage_profile, PhysicalDamageProfile):
        raise WeaponError("Invalid physical damage profile.")
    normalized_key = action_key.strip()
    existing = (
        db.query(CombatAction)
        .filter(
            CombatAction.encounter_id == encounter.id,
            CombatAction.action_key == normalized_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if (
            existing.actor_participant_id != actor.id
            or existing.target_participant_id != target.id
            or existing.action_type != action_type.value
            or existing.technique_id is not None
            or existing.weapon_instance_id != weapon_instance_id
            or existing.physical_damage_profile != damage_profile.value
        ):
            raise CombatActionError(
                "Action key already belongs to another combat action."
            )
        return CombatActionResolution(existing, replayed=True)
    instance = db.get(ItemInstance, weapon_instance_id)
    if instance is None:
        raise WeaponError("Weapon instance does not exist.")
    if (
        instance.location_type != ItemLocationType.CHARACTER_EQUIPPED.value
        or instance.location_ref != actor.actor_id
        or item_accessibility(instance) != ItemAccessibility.IMMEDIATE
    ):
        raise WeaponError("Weapon must be equipped in hand and immediately usable.")
    profile = db.get(ItemWeaponProfile, instance.definition_id)
    if profile is None:
        raise WeaponError("Item has no authoritative weapon profile.")
    if damage_profile not in get_weapon_damage_profiles(profile):
        raise WeaponError("Weapon does not support the selected damage profile.")
    reach = WeaponReach(profile.reach)
    _validate_attack_type(reach, action_type)
    _validate_active_hand(
        WeaponHandRequirement(profile.hand_requirement),
        EquipmentSlot(instance.equipped_slot),
    )
    mechanics = replace(
        basic_attack_mechanics(action_type),
        weapon_instance_id=instance.id,
        physical_damage_profile=damage_profile,
        allowed_target_ranges=_allowed_target_ranges(reach),
    )
    return resolve_profiled_attack(
        db,
        encounter,
        actor,
        target,
        mechanics=mechanics,
        action_key=action_key,
        rng=rng,
    )


def _validate_hand_positions(
    requirement: WeaponHandRequirement,
    slots: frozenset[EquipmentSlot],
) -> None:
    one_hand_slots = {EquipmentSlot.MAIN_HAND, EquipmentSlot.OFF_HAND}
    has_one_hand = bool(slots & one_hand_slots)
    has_two_hands = EquipmentSlot.BOTH_HANDS in slots
    valid = {
        WeaponHandRequirement.ONE_HAND: has_one_hand,
        WeaponHandRequirement.ONE_OR_TWO_HANDS: has_one_hand and has_two_hands,
        WeaponHandRequirement.TWO_HANDS: has_two_hands,
    }[requirement]
    if not valid:
        raise WeaponError(
            "Equipment positions do not satisfy the weapon hand requirement."
        )


def _validate_active_hand(
    requirement: WeaponHandRequirement,
    slot: EquipmentSlot,
) -> None:
    valid_slots = {
        WeaponHandRequirement.ONE_HAND: {
            EquipmentSlot.MAIN_HAND,
            EquipmentSlot.OFF_HAND,
        },
        WeaponHandRequirement.ONE_OR_TWO_HANDS: {
            EquipmentSlot.MAIN_HAND,
            EquipmentSlot.OFF_HAND,
            EquipmentSlot.BOTH_HANDS,
        },
        WeaponHandRequirement.TWO_HANDS: {EquipmentSlot.BOTH_HANDS},
    }[requirement]
    if slot not in valid_slots:
        raise WeaponError("Weapon is not held according to its hand requirement.")


def _validate_attack_type(
    reach: WeaponReach,
    action_type: CombatActionType,
) -> None:
    expected = (
        CombatActionType.RANGED_ATTACK
        if reach == WeaponReach.RANGED
        else CombatActionType.MELEE_ATTACK
    )
    if action_type != expected:
        raise WeaponError("Weapon reach does not support this attack type.")


def _allowed_target_ranges(reach: WeaponReach) -> frozenset[CombatRangeBand]:
    if reach == WeaponReach.RANGED:
        return frozenset(
            {
                CombatRangeBand.ENGAGED,
                CombatRangeBand.NEAR,
                CombatRangeBand.FAR,
            }
        )
    if reach == WeaponReach.LONG:
        return frozenset({CombatRangeBand.ENGAGED, CombatRangeBand.NEAR})
    return frozenset({CombatRangeBand.ENGAGED})


def _encode_damage_profiles(profiles: set[PhysicalDamageProfile]) -> str:
    return json.dumps(
        sorted(profile.value for profile in profiles),
        separators=(",", ":"),
    )
