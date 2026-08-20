import random
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CombatActorType,
    CombatAwareness,
    CombatConditionType,
    CombatEncounterStatus,
    CombatTurnStatus,
    EventType,
)
from app.db.models.combat import CombatEncounter, CombatParticipant, CombatTurn
from app.game.attributes.service import attribute_check_modifier, get_character_attribute
from app.game.dice import d20
from app.game.combat.conditions import (
    consume_participant_turn_conditions,
    has_condition,
    log_condition_triggered,
)
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


_COMPLETION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_AWARENESS_MODIFIERS = {
    CombatAwareness.AWARE.value: 0,
    CombatAwareness.SURPRISED.value: -5,
    CombatAwareness.UNAWARE.value: -10,
}


class CombatTurnError(ValueError):
    pass


@dataclass(frozen=True)
class TurnAdvanceResult:
    completed_turn: CombatTurn
    current_turn: CombatTurn | None
    replayed: bool = False


def roll_initiative(
    db: Session,
    encounter: CombatEncounter,
    *,
    rng: random.Random | None = None,
) -> list[CombatParticipant]:
    """Resolve and persist the initial initiative exactly once."""
    _require_active(encounter)
    participants = _active_participants(db, encounter.id)
    if len(participants) < 2 or len({row.side_key for row in participants}) < 2:
        raise CombatTurnError("Initiative requires active participants on two sides.")
    if encounter.round_number > 0:
        if not all(row.turn_order is not None for row in participants):
            raise CombatTurnError("Persisted initiative is incomplete.")
        return sorted(participants, key=lambda row: row.turn_order or 0)

    for participant in participants:
        _assign_initiative(db, participant, rng=rng)
    participants.sort(key=_initiative_sort_key)
    for order, participant in enumerate(participants):
        participant.turn_order = order

    encounter.round_number = 1
    encounter.current_turn_order = 0
    current = _create_turn(db, encounter, participants[0])
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_INITIATIVE_ROLLED,
        actor_type="combat",
        actor_id=encounter.id,
        payload={
            "encounter_id": encounter.id,
            "round_number": 1,
            "order": [_initiative_payload(row) for row in participants],
            "current_participant_id": current.participant_id,
        },
    )
    db.flush()
    return participants


def enroll_late_participant(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    *,
    rng: random.Random | None = None,
) -> CombatParticipant:
    """Append a late arrival without rewriting already persisted turn slots."""
    if encounter.round_number == 0:
        return participant
    _require_active(encounter)
    _assign_initiative(db, participant, rng=rng)
    maximum = max(
        (
            row.turn_order
            for row in db.query(CombatParticipant)
            .filter(CombatParticipant.encounter_id == encounter.id)
            .all()
            if row.id != participant.id and row.turn_order is not None
        ),
        default=-1,
    )
    participant.turn_order = maximum + 1
    db.flush()
    return participant


def get_current_turn(db: Session, encounter: CombatEncounter) -> CombatTurn | None:
    if encounter.round_number == 0:
        return None
    if encounter.current_turn_order is None:
        return None
    current = _active_turn(db, encounter.id)
    if current is None:
        raise CombatTurnError("Active combat has no persisted current turn.")
    if encounter.status == CombatEncounterStatus.ACTIVE.value:
        current = _skip_unavailable_turns(db, encounter, current)
    return current


def complete_current_turn(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    *,
    completion_key: str,
    advance: bool = True,
) -> TurnAdvanceResult:
    normalized_key = completion_key.strip()
    if not _COMPLETION_KEY_PATTERN.fullmatch(normalized_key):
        raise CombatTurnError("Invalid turn completion key.")

    replay = (
        db.query(CombatTurn)
        .filter(
            CombatTurn.encounter_id == encounter.id,
            CombatTurn.completion_key == normalized_key,
        )
        .one_or_none()
    )
    if replay is not None:
        return TurnAdvanceResult(replay, _active_turn(db, encounter.id), True)

    _require_active(encounter)
    current = get_current_turn(db, encounter)
    if current is None:
        raise CombatTurnError("Initiative has not been rolled.")
    if participant.encounter_id != encounter.id or current.participant_id != participant.id:
        raise CombatTurnError("Only the current participant may complete this turn.")
    if not participant.active:
        raise CombatTurnError("Inactive participant cannot complete a turn.")

    _finish_turn(db, encounter, current, CombatTurnStatus.COMPLETED, normalized_key)
    consume_participant_turn_conditions(db, encounter, participant)
    if advance:
        next_turn = _advance(db, encounter, current.turn_order)
    else:
        encounter.current_turn_order = None
        next_turn = None
    db.flush()
    return TurnAdvanceResult(current, next_turn)


def skip_current_turn_if_inactive(
    db: Session,
    encounter: CombatEncounter,
) -> CombatTurn | None:
    if encounter.round_number == 0 or encounter.status != CombatEncounterStatus.ACTIVE.value:
        return None
    current = _active_turn(db, encounter.id)
    if current is None:
        return None
    return _skip_unavailable_turns(db, encounter, current)


def close_active_turn(db: Session, encounter: CombatEncounter) -> None:
    current = _active_turn(db, encounter.id)
    if current is not None:
        _finish_turn(db, encounter, current, CombatTurnStatus.SKIPPED, None)
    encounter.current_turn_order = None


def _skip_unavailable_turns(
    db: Session,
    encounter: CombatEncounter,
    current: CombatTurn,
) -> CombatTurn | None:
    seen: set[str] = set()
    while True:
        inactive = not current.participant.active
        stunned = (
            not inactive
            and has_condition(
                db,
                current.participant_id,
                CombatConditionType.STUNNED,
            )
        )
        if not inactive and not stunned:
            return current
        if current.id in seen:
            raise CombatTurnError("Combat has no active participant available for a turn.")
        seen.add(current.id)
        if stunned:
            log_condition_triggered(
                db,
                encounter,
                current.participant,
                CombatConditionType.STUNNED,
            )
        _finish_turn(db, encounter, current, CombatTurnStatus.SKIPPED, None)
        if stunned:
            consume_participant_turn_conditions(db, encounter, current.participant)
        current = _advance(db, encounter, current.turn_order)
        if current is None:
            return None


def _advance(
    db: Session,
    encounter: CombatEncounter,
    previous_order: int,
) -> CombatTurn | None:
    participants = sorted(
        _active_participants(db, encounter.id),
        key=lambda row: row.turn_order if row.turn_order is not None else 2**31,
    )
    participants = [row for row in participants if row.turn_order is not None]
    if not participants:
        encounter.current_turn_order = None
        return None
    later = [row for row in participants if (row.turn_order or 0) > previous_order]
    if later:
        next_participant = later[0]
    else:
        encounter.round_number += 1
        next_participant = participants[0]
    encounter.current_turn_order = next_participant.turn_order
    current = _create_turn(db, encounter, next_participant)
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_TURN_ADVANCED,
        actor_type="combat",
        actor_id=encounter.id,
        payload={
            "encounter_id": encounter.id,
            "round_number": encounter.round_number,
            "turn_order": next_participant.turn_order,
            "participant_id": next_participant.id,
        },
    )
    return current


def _assign_initiative(
    db: Session,
    participant: CombatParticipant,
    *,
    rng: random.Random | None,
) -> None:
    base_modifier = 0
    if participant.actor_type == CombatActorType.CHARACTER.value:
        agility = get_character_attribute(
            db,
            participant.actor_id,
            CharacterAttributeKey.AGILITY,
        )
        base_modifier = attribute_check_modifier(agility.value)
    modifier = base_modifier + _AWARENESS_MODIFIERS[participant.awareness]
    result = d20(modifier, rng)
    participant.initiative_roll = result.raw
    participant.initiative_modifier = modifier
    participant.initiative_score = result.total


def _initiative_sort_key(participant: CombatParticipant) -> tuple:
    return (
        -(participant.initiative_score or 0),
        -(participant.initiative_modifier or 0),
        participant.actor_type,
        participant.actor_id,
    )


def _initiative_payload(participant: CombatParticipant) -> dict:
    return {
        "participant_id": participant.id,
        "actor_type": participant.actor_type,
        "actor_id": participant.actor_id,
        "roll": participant.initiative_roll,
        "modifier": participant.initiative_modifier,
        "score": participant.initiative_score,
        "turn_order": participant.turn_order,
    }


def _create_turn(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
) -> CombatTurn:
    turn = CombatTurn(
        encounter_id=encounter.id,
        participant_id=participant.id,
        round_number=encounter.round_number,
        turn_order=participant.turn_order,
        status=CombatTurnStatus.ACTIVE.value,
        started_world_minute=get_world_time(db, encounter.campaign_id).total_minutes(),
    )
    db.add(turn)
    db.flush()
    return turn


def _finish_turn(
    db: Session,
    encounter: CombatEncounter,
    turn: CombatTurn,
    status: CombatTurnStatus,
    completion_key: str | None,
) -> None:
    turn.status = status.value
    turn.completion_key = completion_key
    turn.ended_world_minute = get_world_time(db, encounter.campaign_id).total_minutes()


def _active_turn(db: Session, encounter_id: str) -> CombatTurn | None:
    rows = (
        db.query(CombatTurn)
        .filter(
            CombatTurn.encounter_id == encounter_id,
            CombatTurn.status == CombatTurnStatus.ACTIVE.value,
        )
        .all()
    )
    if len(rows) > 1:
        raise CombatTurnError("Combat has multiple active turns.")
    return rows[0] if rows else None


def _active_participants(db: Session, encounter_id: str) -> list[CombatParticipant]:
    return (
        db.query(CombatParticipant)
        .filter(
            CombatParticipant.encounter_id == encounter_id,
            CombatParticipant.active.is_(True),
        )
        .order_by(CombatParticipant.actor_type, CombatParticipant.actor_id)
        .all()
    )


def _require_active(encounter: CombatEncounter) -> None:
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        raise CombatTurnError("Combat encounter is not active.")
