import random
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CharacterStatus,
    CombatActorType,
    CombatIncapacitationStatus,
    EventType,
    SimulatedPlayerStatus,
)
from app.db.models.character import Character
from app.db.models.combat import (
    CombatAction,
    CombatCriticalCheck,
    CombatEncounter,
    CombatIncapacitation,
    CombatParticipant,
)
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game.attributes.service import attribute_check_modifier, get_character_attribute
from app.game.character.service import kill_character
from app.game.dice import d20
from app.game.players.death import kill_simulated_player
from app.game.time.clock import get_world_time
from app.services.event_log import log_event

CRITICAL_CHECK_DC = 10
REQUIRED_SUCCESSES = 3
MAX_DEATH_FAILURES = 3


class CombatIncapacitationError(ValueError):
    pass


@dataclass(frozen=True)
class CriticalCheckResolution:
    check: CombatCriticalCheck
    incapacitation: CombatIncapacitation


def incapacitate_actor(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    action: CombatAction,
) -> CombatIncapacitation:
    existing = db.query(CombatIncapacitation).filter_by(source_action_id=action.id).one_or_none()
    if existing is not None:
        return existing
    actor = _actor(db, participant)
    _set_incapacitated(participant, actor)
    world_minute = get_world_time(db, encounter.campaign_id).total_minutes()
    state = CombatIncapacitation(
        encounter_id=encounter.id,
        participant_id=participant.id,
        source_action_id=action.id,
        actor_type=participant.actor_type,
        actor_id=participant.actor_id,
        status=CombatIncapacitationStatus.CRITICAL.value,
        created_world_minute=world_minute,
    )
    db.add(state)
    db.flush()
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_PARTICIPANT_INCAPACITATED,
        actor_type=participant.actor_type.lower(),
        actor_id=participant.actor_id,
        payload={
            "encounter_id": encounter.id,
            "participant_id": participant.id,
            "incapacitation_id": state.id,
            "source_action_id": action.id,
        },
        importance=4,
        occurred_world_minute=world_minute,
    )
    return state


def resolve_critical_check(
    db: Session,
    incapacitation: CombatIncapacitation,
    *,
    check_key: str,
    rng: random.Random | None = None,
) -> CriticalCheckResolution:
    key = check_key.strip()
    if not key:
        raise CombatIncapacitationError("Critical check key is required.")
    existing = db.query(CombatCriticalCheck).filter_by(
        incapacitation_id=incapacitation.id, check_key=key
    ).one_or_none()
    if existing is not None:
        return CriticalCheckResolution(existing, incapacitation)
    if incapacitation.status != CombatIncapacitationStatus.CRITICAL.value:
        raise CombatIncapacitationError("Only a critical actor can make a critical check.")

    actor = _actor_by_identity(db, incapacitation.actor_type, incapacitation.actor_id)
    modifier = _critical_modifier(db, incapacitation.actor_type, incapacitation.actor_id)
    result = d20(modifier, rng)
    successes_before = incapacitation.stabilization_successes
    failures_before = incapacitation.death_failures
    success = result.raw == 20 or (result.raw != 1 and result.total >= CRITICAL_CHECK_DC)
    if result.raw == 20:
        incapacitation.stabilization_successes = REQUIRED_SUCCESSES
        outcome = "NATURAL_20"
    elif result.raw == 1:
        incapacitation.death_failures += 2
        outcome = "NATURAL_1"
    elif success:
        incapacitation.stabilization_successes += 1
        outcome = "SUCCESS"
    else:
        incapacitation.death_failures += 1
        outcome = "FAILURE"

    world_minute = get_world_time(db, _encounter(db, incapacitation).campaign_id).total_minutes()
    check = CombatCriticalCheck(
        incapacitation_id=incapacitation.id,
        check_key=key,
        roll=result.raw,
        modifier=modifier,
        total=result.total,
        dc=CRITICAL_CHECK_DC,
        success=success,
        successes_before=successes_before,
        successes_after=incapacitation.stabilization_successes,
        failures_before=failures_before,
        failures_after=incapacitation.death_failures,
        outcome=outcome,
        created_world_minute=world_minute,
    )
    db.add(check)
    db.flush()
    campaign_id = _encounter(db, incapacitation).campaign_id
    log_event(
        db,
        campaign_id,
        EventType.COMBAT_CRITICAL_CHECK_RESOLVED,
        actor_type=incapacitation.actor_type.lower(),
        actor_id=incapacitation.actor_id,
        payload={
            "incapacitation_id": incapacitation.id,
            "check_id": check.id,
            "roll": result.raw,
            "modifier": modifier,
            "total": result.total,
            "dc": CRITICAL_CHECK_DC,
            "outcome": outcome,
            "successes": incapacitation.stabilization_successes,
            "death_failures": incapacitation.death_failures,
        },
        occurred_world_minute=world_minute,
    )
    if incapacitation.death_failures >= MAX_DEATH_FAILURES:
        _permanently_kill(db, campaign_id, incapacitation, actor, f"critical_checks:{check.id}")
        incapacitation.status = CombatIncapacitationStatus.DEAD.value
        incapacitation.resolution_reason = f"critical_checks:{check.id}"
        incapacitation.resolved_world_minute = world_minute
    elif incapacitation.stabilization_successes >= REQUIRED_SUCCESSES:
        incapacitation.status = CombatIncapacitationStatus.STABILIZED.value
        incapacitation.resolution_reason = f"stabilized:{check.id}"
        incapacitation.resolved_world_minute = world_minute
        log_event(
            db,
            campaign_id,
            EventType.COMBAT_PARTICIPANT_STABILIZED,
            actor_type=incapacitation.actor_type.lower(),
            actor_id=incapacitation.actor_id,
            payload={"incapacitation_id": incapacitation.id, "check_id": check.id},
            importance=3,
            occurred_world_minute=world_minute,
        )
    db.flush()
    return CriticalCheckResolution(check, incapacitation)


def recover_stabilized_actor(
    db: Session,
    incapacitation: CombatIncapacitation,
    *,
    recovery_key: str,
    hp_restored: float = 1,
) -> CombatIncapacitation:
    key = recovery_key.strip()
    if not key:
        raise CombatIncapacitationError("Recovery key is required.")
    if incapacitation.status == CombatIncapacitationStatus.RECOVERED.value:
        if incapacitation.recovery_key == key:
            return incapacitation
        raise CombatIncapacitationError("This incapacitation was already recovered.")
    if incapacitation.status != CombatIncapacitationStatus.STABILIZED.value:
        raise CombatIncapacitationError("The actor must be stabilized before recovery.")
    actor = _actor_by_identity(db, incapacitation.actor_type, incapacitation.actor_id)
    restored = max(1.0, hp_restored)
    actor.hp_current = min(float(actor.hp_max), restored)
    if incapacitation.actor_type == CombatActorType.CHARACTER.value:
        actor.status = CharacterStatus.ALIVE.value
    elif incapacitation.actor_type == CombatActorType.NPC.value:
        actor.incapacitated = False
    else:
        actor.status = SimulatedPlayerStatus.ACTIVE.value
    world_minute = get_world_time(db, _encounter(db, incapacitation).campaign_id).total_minutes()
    incapacitation.status = CombatIncapacitationStatus.RECOVERED.value
    incapacitation.recovery_key = key
    incapacitation.resolution_reason = f"recovered:{key}"
    incapacitation.resolved_world_minute = world_minute
    log_event(
        db,
        _encounter(db, incapacitation).campaign_id,
        EventType.COMBAT_PARTICIPANT_RECOVERED,
        actor_type=incapacitation.actor_type.lower(),
        actor_id=incapacitation.actor_id,
        payload={"incapacitation_id": incapacitation.id, "hp_restored": actor.hp_current},
        importance=3,
        occurred_world_minute=world_minute,
    )
    db.flush()
    return incapacitation


def kill_devastated_actor(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    *,
    cause: str,
) -> None:
    _permanently_kill(db, encounter.campaign_id, None, _actor(db, participant), cause, participant.actor_type)


def _set_incapacitated(participant: CombatParticipant, actor: Character | NPC | SimulatedPlayer) -> None:
    if participant.actor_type == CombatActorType.CHARACTER.value:
        actor.status = CharacterStatus.INCAPACITATED.value
    elif participant.actor_type == CombatActorType.NPC.value:
        actor.incapacitated = True
    else:
        actor.status = SimulatedPlayerStatus.INCAPACITATED.value


def _permanently_kill(db, campaign_id, state, actor, cause, actor_type=None) -> None:
    identity = actor_type or state.actor_type
    if identity == CombatActorType.CHARACTER.value:
        kill_character(db, campaign_id, actor, cause=cause)
    elif identity == CombatActorType.NPC.value:
        actor.incapacitated = False
        actor.alive = False
        log_event(db, campaign_id, EventType.NPC_DIED, actor_type="npc", actor_id=actor.id,
                  payload={"npc_id": actor.id, "name": actor.name, "cause": cause}, importance=5)
    else:
        kill_simulated_player(db, campaign_id, actor, cause=cause)


def _critical_modifier(db: Session, actor_type: str, actor_id: str) -> int:
    if actor_type != CombatActorType.CHARACTER.value:
        return 0
    return attribute_check_modifier(get_character_attribute(db, actor_id, CharacterAttributeKey.VITALITY).value)


def _actor(db: Session, participant: CombatParticipant):
    return _actor_by_identity(db, participant.actor_type, participant.actor_id)


def _actor_by_identity(db: Session, actor_type: str, actor_id: str):
    model = {CombatActorType.CHARACTER.value: Character, CombatActorType.NPC.value: NPC,
             CombatActorType.SIMULATED_PLAYER.value: SimulatedPlayer}.get(actor_type)
    actor = db.get(model, actor_id) if model else None
    if actor is None:
        raise CombatIncapacitationError("Critical actor does not exist.")
    return actor


def _encounter(db: Session, state: CombatIncapacitation) -> CombatEncounter:
    encounter = db.get(CombatEncounter, state.encounter_id)
    if encounter is None:
        raise CombatIncapacitationError("Critical encounter does not exist.")
    return encounter
