import random
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActionOutcome,
    CombatActionType,
    CombatActorType,
    CombatConditionType,
    CombatDamageType,
    CombatEncounterStatus,
    CombatRangeBand,
    EventType,
    PhysicalDamageProfile,
)
from app.db.models.combat import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
    CombatTacticalAction,
)
from app.game.attributes.service import attribute_check_modifier, get_character_attribute
from app.game.combat.turns import complete_current_turn, get_current_turn
from app.game.combat.damage import apply_attack_damage
from app.game.combat.encounters import end_encounter
from app.game.combat.costs import apply_action_cost, validate_resource_cost
from app.game.combat.conditions import has_condition
from app.game.dice import d20
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


BASE_DEFENSE = 10
ENGAGED_RANGED_PENALTY = -2
WEAKENED_ATTACK_PENALTY = -2
EXPOSED_DEFENSE_PENALTY = -2
DEFENSIVE_STANCE_BONUS = 2
_ACTION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class CombatActionError(ValueError):
    pass


@dataclass(frozen=True)
class CombatActionResolution:
    action: CombatAction
    replayed: bool = False


@dataclass(frozen=True)
class AttackMechanics:
    action_type: CombatActionType
    attack_attribute: CharacterAttributeKey
    resource_key: CharacterResourceKey
    resource_cost: float
    base_damage_dice: int
    damage_die_sides: int
    damage_attribute: CharacterAttributeKey
    damage_type: CombatDamageType = CombatDamageType.PHYSICAL
    technique_id: str | None = None
    weapon_instance_id: str | None = None
    physical_damage_profile: PhysicalDamageProfile | None = None
    allowed_target_ranges: frozenset[CombatRangeBand] | None = None


def resolve_attack(
    db: Session,
    encounter: CombatEncounter,
    actor: CombatParticipant,
    target: CombatParticipant,
    *,
    action_type: CombatActionType,
    action_key: str,
    rng: random.Random | None = None,
) -> CombatActionResolution:
    """Resolve one basic attack, apply its damage and consume its turn."""
    if not isinstance(action_type, CombatActionType):
        raise CombatActionError("Invalid combat action type.")
    mechanics = basic_attack_mechanics(action_type)
    return resolve_profiled_attack(
        db,
        encounter,
        actor,
        target,
        mechanics=mechanics,
        action_key=action_key,
        rng=rng,
    )


def resolve_profiled_attack(
    db: Session,
    encounter: CombatEncounter,
    actor: CombatParticipant,
    target: CombatParticipant,
    *,
    mechanics: AttackMechanics,
    action_key: str,
    rng: random.Random | None = None,
) -> CombatActionResolution:
    """Resolve an already-authorized immutable attack profile."""
    action_type = mechanics.action_type
    if not isinstance(action_type, CombatActionType):
        raise CombatActionError("Invalid combat action type.")
    if not isinstance(mechanics.attack_attribute, CharacterAttributeKey):
        raise CombatActionError("Invalid attack attribute.")
    if not isinstance(mechanics.damage_attribute, CharacterAttributeKey):
        raise CombatActionError("Invalid damage attribute.")
    if mechanics.attack_attribute == CharacterAttributeKey.LUCK:
        raise CombatActionError("Luck cannot resolve a combat attack.")
    if mechanics.damage_attribute == CharacterAttributeKey.LUCK:
        raise CombatActionError("Luck cannot determine combat damage.")
    if not isinstance(mechanics.damage_type, CombatDamageType):
        raise CombatActionError("Invalid combat damage type.")
    if (mechanics.weapon_instance_id is None) != (
        mechanics.physical_damage_profile is None
    ):
        raise CombatActionError("Weapon attacks require complete weapon mechanics.")
    if (
        mechanics.physical_damage_profile is not None
        and not isinstance(mechanics.physical_damage_profile, PhysicalDamageProfile)
    ):
        raise CombatActionError("Invalid physical weapon damage profile.")
    if mechanics.base_damage_dice < 1 or mechanics.damage_die_sides < 2:
        raise CombatActionError("Invalid combat damage dice.")
    if mechanics.allowed_target_ranges is not None and any(
        not isinstance(range_band, CombatRangeBand)
        for range_band in mechanics.allowed_target_ranges
    ):
        raise CombatActionError("Invalid weapon target ranges.")
    if (mechanics.weapon_instance_id is None) != (
        mechanics.allowed_target_ranges is None
    ):
        raise CombatActionError("Weapon attacks require authoritative target ranges.")
    normalized_key = action_key.strip()
    if not _ACTION_KEY_PATTERN.fullmatch(normalized_key):
        raise CombatActionError("Invalid combat action key.")
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
            or existing.technique_id != mechanics.technique_id
            or existing.weapon_instance_id != mechanics.weapon_instance_id
            or existing.physical_damage_profile
            != (
                mechanics.physical_damage_profile.value
                if mechanics.physical_damage_profile
                else None
            )
        ):
            raise CombatActionError("Action key already belongs to another combat action.")
        return CombatActionResolution(existing, replayed=True)

    _validate_attack(encounter, actor, target, mechanics)
    current_turn = get_current_turn(db, encounter)
    if current_turn is None:
        raise CombatActionError("Initiative has not been rolled.")
    if current_turn.participant_id != actor.id:
        raise CombatActionError("Only the current participant may resolve an attack.")
    if (
        db.query(CombatAction)
        .filter(CombatAction.turn_id == current_turn.id)
        .one_or_none()
        is not None
    ):
        raise CombatActionError("Current turn already has a resolved combat action.")
    if (
        db.query(CombatTacticalAction)
        .filter(CombatTacticalAction.turn_id == current_turn.id)
        .one_or_none()
        is not None
    ):
        raise CombatActionError("Current turn already has a resolved tactical action.")
    resource_cost = validate_resource_cost(
        db,
        actor,
        mechanics.resource_key,
        mechanics.resource_cost,
    )

    attack_attribute = mechanics.attack_attribute
    attack_modifier = _attribute_modifier(db, actor, attack_attribute)
    if has_condition(db, actor.id, CombatConditionType.WEAKENED):
        attack_modifier += WEAKENED_ATTACK_PENALTY
    if (
        action_type == CombatActionType.RANGED_ATTACK
        and target.range_band == CombatRangeBand.ENGAGED.value
    ):
        attack_modifier += ENGAGED_RANGED_PENALTY
    defense_modifier = _attribute_modifier(
        db,
        target,
        CharacterAttributeKey.AGILITY,
    )
    if has_condition(db, target.id, CombatConditionType.EXPOSED):
        defense_modifier += EXPOSED_DEFENSE_PENALTY
    if has_condition(
        db, target.id, CombatConditionType.GUARDED
    ) or has_condition(db, target.id, CombatConditionType.DODGING):
        defense_modifier += DEFENSIVE_STANCE_BONUS
    defense_total = BASE_DEFENSE + defense_modifier
    roll = d20(attack_modifier, rng)
    outcome = _resolve_outcome(roll.raw, roll.total, defense_total)
    world_minute = get_world_time(db, encounter.campaign_id).total_minutes()
    action = CombatAction(
        encounter_id=encounter.id,
        turn_id=current_turn.id,
        actor_participant_id=actor.id,
        target_participant_id=target.id,
        action_key=normalized_key,
        action_type=action_type.value,
        technique_id=mechanics.technique_id,
        weapon_instance_id=mechanics.weapon_instance_id,
        physical_damage_profile=(
            mechanics.physical_damage_profile.value
            if mechanics.physical_damage_profile
            else None
        ),
        attack_attribute=attack_attribute.value,
        target_range_band=target.range_band,
        attack_roll=roll.raw,
        attack_modifier=attack_modifier,
        attack_total=roll.total,
        defense_base=BASE_DEFENSE,
        defense_modifier=defense_modifier,
        defense_total=defense_total,
        outcome=outcome.value,
        base_damage_dice=mechanics.base_damage_dice,
        damage_die_sides=mechanics.damage_die_sides,
        damage_attribute=mechanics.damage_attribute.value,
        damage_type=mechanics.damage_type.value,
        created_world_minute=world_minute,
    )
    db.add(action)
    db.flush()
    apply_action_cost(db, encounter, action, actor, resource_cost)
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_ACTION_RESOLVED,
        actor_type=actor.actor_type.lower(),
        actor_id=actor.actor_id,
        payload={
            "encounter_id": encounter.id,
            "turn_id": current_turn.id,
            "action_id": action.id,
            "action_key": normalized_key,
            "action_type": action_type.value,
            "technique_id": mechanics.technique_id,
            "weapon_instance_id": mechanics.weapon_instance_id,
            "physical_damage_profile": (
                mechanics.physical_damage_profile.value
                if mechanics.physical_damage_profile
                else None
            ),
            "actor_participant_id": actor.id,
            "target_participant_id": target.id,
            "attack_attribute": attack_attribute.value,
            "target_range_band": target.range_band,
            "roll": roll.raw,
            "modifier": attack_modifier,
            "total": roll.total,
            "defense": defense_total,
            "outcome": outcome.value,
            "resource_key": action.resource_key,
            "resource_cost": action.resource_cost,
            "resource_before": action.resource_before,
            "resource_after": action.resource_after,
        },
    )
    damage = apply_attack_damage(
        db,
        encounter,
        action,
        actor,
        target,
        rng=rng,
    )
    complete_current_turn(
        db,
        encounter,
        actor,
        completion_key=normalized_key,
        advance=not damage.encounter_should_end,
    )
    if damage.encounter_should_end:
        status = (
            CombatEncounterStatus.DEFEAT
            if target.actor_type == CombatActorType.CHARACTER.value
            else CombatEncounterStatus.VICTORY
        )
        end_encounter(
            db,
            encounter,
            status,
            reason=f"side:{actor.side_key}",
        )
    db.flush()
    return CombatActionResolution(action)


def _validate_attack(
    encounter: CombatEncounter,
    actor: CombatParticipant,
    target: CombatParticipant,
    mechanics: AttackMechanics,
) -> None:
    action_type = mechanics.action_type
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        raise CombatActionError("Combat encounter is not active.")
    if actor.encounter_id != encounter.id or target.encounter_id != encounter.id:
        raise CombatActionError("Attack participants must belong to the encounter.")
    if not actor.active or not target.active:
        raise CombatActionError("Attack participants must be active.")
    if actor.id == target.id:
        raise CombatActionError("A participant cannot attack itself.")
    if actor.side_key == target.side_key:
        raise CombatActionError("A participant cannot attack its own side.")
    target_range = CombatRangeBand(target.range_band)
    if mechanics.allowed_target_ranges is not None:
        if target_range not in mechanics.allowed_target_ranges:
            raise CombatActionError("Target is outside this weapon's reach.")
        return
    if action_type == CombatActionType.MELEE_ATTACK:
        if target_range != CombatRangeBand.ENGAGED:
            raise CombatActionError("Melee attack requires an engaged target.")
    elif target_range == CombatRangeBand.OUT_OF_REACH:
        raise CombatActionError("Target is out of ranged attack reach.")


def basic_attack_mechanics(action_type: CombatActionType) -> AttackMechanics:
    if not isinstance(action_type, CombatActionType):
        raise CombatActionError("Invalid combat action type.")
    attribute = _attack_attribute(action_type)
    return AttackMechanics(
        action_type=action_type,
        attack_attribute=attribute,
        resource_key=CharacterResourceKey.STAMINA,
        resource_cost=(
            2.0 if action_type == CombatActionType.MELEE_ATTACK else 1.0
        ),
        base_damage_dice=1,
        damage_die_sides=6,
        damage_attribute=attribute,
    )


def _attack_attribute(action_type: CombatActionType) -> CharacterAttributeKey:
    if action_type == CombatActionType.MELEE_ATTACK:
        return CharacterAttributeKey.STRENGTH
    return CharacterAttributeKey.AGILITY


def _attribute_modifier(
    db: Session,
    participant: CombatParticipant,
    key: CharacterAttributeKey,
) -> int:
    if participant.actor_type != CombatActorType.CHARACTER.value:
        return 0
    attribute = get_character_attribute(db, participant.actor_id, key)
    return attribute_check_modifier(attribute.value)


def _resolve_outcome(
    raw_roll: int,
    attack_total: int,
    defense_total: int,
) -> CombatActionOutcome:
    if raw_roll == 1:
        return CombatActionOutcome.CRITICAL_MISS
    if raw_roll == 20:
        return CombatActionOutcome.CRITICAL_HIT
    if attack_total >= defense_total:
        return CombatActionOutcome.HIT
    return CombatActionOutcome.MISS
