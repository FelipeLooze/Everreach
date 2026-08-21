import json
import random
from dataclasses import replace

from sqlalchemy.orm import Session

from app.core.enums import (
    BodyArea,
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
from app.game.items.durability import is_item_broken
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
    target_body_area: BodyArea = BodyArea.TORSO,
    rng: random.Random | None = None,
) -> CombatActionResolution:
    if actor.actor_type != CombatActorType.CHARACTER.value:
        raise WeaponError("Only a character can use character equipment.")
    if not isinstance(action_type, CombatActionType):
        raise WeaponError("Invalid weapon attack type.")
    if not isinstance(damage_profile, PhysicalDamageProfile):
        raise WeaponError("Invalid physical damage profile.")
    if not isinstance(target_body_area, BodyArea):
        raise WeaponError("Invalid target body area.")
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
            or existing.target_body_area != target_body_area.value
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
    if is_item_broken(instance):
        raise WeaponError("Broken weapon cannot resolve an attack.")
    profile = db.get(ItemWeaponProfile, instance.definition_id)
    if profile is None:
        raise WeaponError("Item has no authoritative weapon profile.")
    if damage_profile not in get_weapon_damage_profiles(profile):
        raise WeaponError("Weapon does not support the selected damage profile.")
    reach = WeaponReach(profile.reach)
    validate_attack_type_matches_reach(reach, action_type)
    _validate_active_hand(
        WeaponHandRequirement(profile.hand_requirement),
        EquipmentSlot(instance.equipped_slot),
    )
    mechanics = replace(
        basic_attack_mechanics(action_type),
        weapon_instance_id=instance.id,
        physical_damage_profile=damage_profile,
        target_body_area=target_body_area,
        allowed_target_ranges=allowed_target_ranges_for_reach(reach),
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


def validate_attack_type_matches_reach(
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


def allowed_target_ranges_for_reach(reach: WeaponReach) -> frozenset[CombatRangeBand]:
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


def find_equipped_weapon(
    db: Session,
    character_id: str,
    *,
    weapon_family: WeaponFamily,
) -> tuple[ItemInstance, ItemWeaponProfile] | None:
    """The character's currently equipped, immediately-usable weapon of this
    family, if any. Read-only counterpart to resolve_weapon_attack's own
    equipped-weapon validation — reused by technique resolution (11E) so a
    technique that requires a weapon checks the same real equipment state,
    not a separate notion of "having" it."""
    candidates = (
        db.query(ItemInstance)
        .filter(
            ItemInstance.location_type == ItemLocationType.CHARACTER_EQUIPPED.value,
            ItemInstance.location_ref == character_id,
        )
        .all()
    )
    for instance in candidates:
        if item_accessibility(instance) != ItemAccessibility.IMMEDIATE:
            continue
        if is_item_broken(instance):
            continue
        profile = db.get(ItemWeaponProfile, instance.definition_id)
        if profile is None or profile.weapon_family != weapon_family.value:
            continue
        return instance, profile
    return None


def resolve_technique_weapon_requirement(
    db: Session,
    character_id: str,
    *,
    required_weapon_family: WeaponFamily,
    action_type: CombatActionType,
) -> tuple[str, frozenset[CombatRangeBand]]:
    """Find and validate the weapon a technique requires, returning
    (weapon_instance_id, allowed_target_ranges) for its AttackMechanics.
    Raises WeaponError if no matching weapon is equipped and usable, or if
    the weapon's reach doesn't support the technique's attack type."""
    found = find_equipped_weapon(db, character_id, weapon_family=required_weapon_family)
    if found is None:
        raise WeaponError(
            f"No {required_weapon_family.value.title()} is equipped and ready to use."
        )
    instance, profile = found
    reach = WeaponReach(profile.reach)
    validate_attack_type_matches_reach(reach, action_type)
    return instance.id, allowed_target_ranges_for_reach(reach)


def _encode_damage_profiles(profiles: set[PhysicalDamageProfile]) -> str:
    return json.dumps(
        sorted(profile.value for profile in profiles),
        separators=(",", ":"),
    )
