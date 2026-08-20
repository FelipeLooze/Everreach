import random
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CombatActionOutcome,
    CombatActionType,
    CombatActorType,
    CombatEncounterStatus,
    CombatRangeBand,
    EventType,
)
from app.db.models.combat import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
)
from app.game.attributes.service import attribute_check_modifier, get_character_attribute
from app.game.combat.turns import complete_current_turn, get_current_turn
from app.game.dice import d20
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


BASE_DEFENSE = 10
ENGAGED_RANGED_PENALTY = -2
_ACTION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class CombatActionError(ValueError):
    pass


@dataclass(frozen=True)
class CombatActionResolution:
    action: CombatAction
    replayed: bool = False


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
    """Resolve one basic attack and consume its turn, without applying damage."""
    normalized_key = action_key.strip()
    if not _ACTION_KEY_PATTERN.fullmatch(normalized_key):
        raise CombatActionError("Invalid combat action key.")
    if not isinstance(action_type, CombatActionType):
        raise CombatActionError("Invalid combat action type.")

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
        ):
            raise CombatActionError("Action key already belongs to another combat action.")
        return CombatActionResolution(existing, replayed=True)

    _validate_attack(encounter, actor, target, action_type)
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

    attack_attribute = _attack_attribute(action_type)
    attack_modifier = _attribute_modifier(db, actor, attack_attribute)
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
        attack_attribute=attack_attribute.value,
        target_range_band=target.range_band,
        attack_roll=roll.raw,
        attack_modifier=attack_modifier,
        attack_total=roll.total,
        defense_base=BASE_DEFENSE,
        defense_modifier=defense_modifier,
        defense_total=defense_total,
        outcome=outcome.value,
        created_world_minute=world_minute,
    )
    db.add(action)
    db.flush()
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
            "actor_participant_id": actor.id,
            "target_participant_id": target.id,
            "attack_attribute": attack_attribute.value,
            "target_range_band": target.range_band,
            "roll": roll.raw,
            "modifier": attack_modifier,
            "total": roll.total,
            "defense": defense_total,
            "outcome": outcome.value,
        },
    )
    complete_current_turn(
        db,
        encounter,
        actor,
        completion_key=normalized_key,
    )
    db.flush()
    return CombatActionResolution(action)


def _validate_attack(
    encounter: CombatEncounter,
    actor: CombatParticipant,
    target: CombatParticipant,
    action_type: CombatActionType,
) -> None:
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
    if action_type == CombatActionType.MELEE_ATTACK:
        if target_range != CombatRangeBand.ENGAGED:
            raise CombatActionError("Melee attack requires an engaged target.")
    elif target_range == CombatRangeBand.OUT_OF_REACH:
        raise CombatActionError("Target is out of ranged attack reach.")


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
