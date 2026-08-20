import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatConditionType,
    CombatEncounterStatus,
    EventType,
)
from app.db.models.combat import (
    CombatAction,
    CombatCondition,
    CombatEncounter,
    CombatParticipant,
)
from app.services.event_log import log_event


MAX_CONDITION_TURNS = 10
_APPLICATION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class CombatConditionError(ValueError):
    pass


@dataclass(frozen=True)
class ConditionApplicationResult:
    condition: CombatCondition
    replayed: bool = False


def apply_condition(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    *,
    condition_type: CombatConditionType,
    duration_turns: int,
    application_key: str,
    source_action: CombatAction | None = None,
) -> ConditionApplicationResult:
    normalized_key = application_key.strip()
    if not _APPLICATION_KEY_PATTERN.fullmatch(normalized_key):
        raise CombatConditionError("Invalid condition application key.")
    if not isinstance(condition_type, CombatConditionType):
        raise CombatConditionError("Invalid combat condition type.")
    if not 1 <= duration_turns <= MAX_CONDITION_TURNS:
        raise CombatConditionError(
            f"Condition duration must be between 1 and {MAX_CONDITION_TURNS} turns."
        )
    existing = (
        db.query(CombatCondition)
        .filter(
            CombatCondition.encounter_id == encounter.id,
            CombatCondition.application_key == normalized_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if (
            existing.participant_id != participant.id
            or existing.condition_type != condition_type.value
            or existing.source_action_id != (source_action.id if source_action else None)
        ):
            raise CombatConditionError(
                "Application key already belongs to another condition."
            )
        return ConditionApplicationResult(existing, replayed=True)
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        raise CombatConditionError("Combat encounter is not active.")
    if participant.encounter_id != encounter.id or not participant.active:
        raise CombatConditionError("Condition target must be active in encounter.")
    if source_action is not None and source_action.encounter_id != encounter.id:
        raise CombatConditionError("Condition source action belongs to another encounter.")

    condition = CombatCondition(
        encounter_id=encounter.id,
        participant_id=participant.id,
        source_action_id=source_action.id if source_action else None,
        application_key=normalized_key,
        condition_type=condition_type.value,
        remaining_turns=duration_turns,
        applied_round=encounter.round_number,
        active=True,
        removal_reason="",
    )
    db.add(condition)
    db.flush()
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_CONDITION_APPLIED,
        actor_type=participant.actor_type.lower(),
        actor_id=participant.actor_id,
        payload={
            "encounter_id": encounter.id,
            "condition_id": condition.id,
            "participant_id": participant.id,
            "condition_type": condition_type.value,
            "duration_turns": duration_turns,
            "source_action_id": condition.source_action_id,
        },
    )
    db.flush()
    return ConditionApplicationResult(condition)


def active_conditions(
    db: Session,
    participant_id: str,
    condition_type: CombatConditionType | None = None,
) -> list[CombatCondition]:
    query = db.query(CombatCondition).filter(
        CombatCondition.participant_id == participant_id,
        CombatCondition.active.is_(True),
    )
    if condition_type is not None:
        query = query.filter(CombatCondition.condition_type == condition_type.value)
    return query.order_by(CombatCondition.id).all()


def has_condition(
    db: Session,
    participant_id: str,
    condition_type: CombatConditionType,
) -> bool:
    return bool(active_conditions(db, participant_id, condition_type))


def consume_participant_turn_conditions(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
) -> None:
    for condition in active_conditions(db, participant.id):
        condition.remaining_turns -= 1
        if condition.remaining_turns <= 0:
            _deactivate_condition(
                db,
                encounter,
                condition,
                reason="duration_expired",
                event_type=EventType.COMBAT_CONDITION_EXPIRED,
            )
    db.flush()


def log_condition_triggered(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    condition_type: CombatConditionType,
) -> None:
    condition_ids = [
        row.id for row in active_conditions(db, participant.id, condition_type)
    ]
    if not condition_ids:
        return
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_CONDITION_TRIGGERED,
        actor_type=participant.actor_type.lower(),
        actor_id=participant.actor_id,
        payload={
            "encounter_id": encounter.id,
            "participant_id": participant.id,
            "condition_type": condition_type.value,
            "condition_ids": condition_ids,
        },
    )


def remove_condition(
    db: Session,
    encounter: CombatEncounter,
    condition: CombatCondition,
    *,
    reason: str,
) -> CombatCondition:
    if condition.encounter_id != encounter.id:
        raise CombatConditionError("Condition does not belong to encounter.")
    normalized_reason = " ".join(reason.split())
    if not normalized_reason:
        raise CombatConditionError("Condition removal reason is required.")
    if not condition.active:
        return condition
    _deactivate_condition(
        db,
        encounter,
        condition,
        reason=normalized_reason,
        event_type=EventType.COMBAT_CONDITION_REMOVED,
    )
    db.flush()
    return condition


def remove_participant_conditions(
    db: Session,
    encounter: CombatEncounter,
    participant: CombatParticipant,
    *,
    reason: str,
) -> None:
    for condition in active_conditions(db, participant.id):
        _deactivate_condition(
            db,
            encounter,
            condition,
            reason=reason,
            event_type=EventType.COMBAT_CONDITION_REMOVED,
        )
    db.flush()


def remove_encounter_conditions(
    db: Session,
    encounter: CombatEncounter,
    *,
    reason: str,
) -> None:
    rows = (
        db.query(CombatCondition)
        .filter(
            CombatCondition.encounter_id == encounter.id,
            CombatCondition.active.is_(True),
        )
        .order_by(CombatCondition.id)
        .all()
    )
    for condition in rows:
        _deactivate_condition(
            db,
            encounter,
            condition,
            reason=reason,
            event_type=EventType.COMBAT_CONDITION_REMOVED,
        )
    db.flush()


def _deactivate_condition(
    db: Session,
    encounter: CombatEncounter,
    condition: CombatCondition,
    *,
    reason: str,
    event_type: EventType,
) -> None:
    condition.active = False
    condition.remaining_turns = 0
    condition.removed_round = encounter.round_number
    condition.removal_reason = reason
    log_event(
        db,
        encounter.campaign_id,
        event_type,
        actor_type=condition.participant.actor_type.lower(),
        actor_id=condition.participant.actor_id,
        payload={
            "encounter_id": encounter.id,
            "condition_id": condition.id,
            "participant_id": condition.participant_id,
            "condition_type": condition.condition_type,
            "reason": reason,
        },
    )
