import random
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActorType,
    CombatConditionType,
    CombatEncounterStatus,
    CombatRangeBand,
    CombatTacticalActionType,
    EventType,
)
from app.db.models.character import Character
from app.db.models.combat import (
    CombatAction,
    CombatCondition,
    CombatEncounter,
    CombatParticipant,
    CombatTacticalAction,
)
from app.game.attributes.service import attribute_check_modifier, get_character_attribute
from app.game.combat.conditions import apply_condition
from app.game.combat.costs import apply_action_cost, validate_resource_cost
from app.game.combat.encounters import end_encounter, list_active_participants, remove_participant
from app.game.combat.turns import complete_current_turn, get_current_turn
from app.game.dice import d20
from app.game.items.encumbrance import get_character_encumbrance
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


FLEE_DC = 12
_ACTION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ACTION_COSTS = {
    CombatTacticalActionType.GUARD: 1.0,
    CombatTacticalActionType.DODGE: 2.0,
    CombatTacticalActionType.APPROACH: 1.0,
    CombatTacticalActionType.RETREAT: 1.0,
    CombatTacticalActionType.DISENGAGE: 1.0,
    CombatTacticalActionType.FLEE: 2.0,
    CombatTacticalActionType.WAIT: 0.0,
}
_DEFENSIVE_CONDITIONS = {
    CombatTacticalActionType.GUARD: CombatConditionType.GUARDED,
    CombatTacticalActionType.DODGE: CombatConditionType.DODGING,
}


class CombatTacticalActionError(ValueError):
    pass


@dataclass(frozen=True)
class TacticalActionResolution:
    action: CombatTacticalAction
    condition: CombatCondition | None = None
    replayed: bool = False


def resolve_tactical_action(
    db: Session,
    encounter: CombatEncounter,
    actor: CombatParticipant,
    *,
    action_type: CombatTacticalActionType,
    action_key: str,
    target: CombatParticipant | None = None,
    rng: random.Random | None = None,
) -> TacticalActionResolution:
    normalized_key = action_key.strip()
    if not _ACTION_KEY_PATTERN.fullmatch(normalized_key):
        raise CombatTacticalActionError("Invalid tactical action key.")
    if not isinstance(action_type, CombatTacticalActionType):
        raise CombatTacticalActionError("Invalid tactical action type.")
    existing = (
        db.query(CombatTacticalAction)
        .filter(
            CombatTacticalAction.encounter_id == encounter.id,
            CombatTacticalAction.action_key == normalized_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if (
            existing.actor_participant_id != actor.id
            or existing.target_participant_id != (target.id if target else None)
            or existing.action_type != action_type.value
        ):
            raise CombatTacticalActionError(
                "Action key already belongs to another tactical action."
            )
        condition = (
            db.query(CombatCondition)
            .filter(CombatCondition.source_tactical_action_id == existing.id)
            .one_or_none()
        )
        return TacticalActionResolution(existing, condition, replayed=True)

    _validate_actor_and_target(encounter, actor, target, action_type)
    current_turn = get_current_turn(db, encounter)
    if current_turn is None:
        raise CombatTacticalActionError("Initiative has not been rolled.")
    if current_turn.participant_id != actor.id:
        raise CombatTacticalActionError(
            "Only the current participant may resolve a tactical action."
        )
    if (
        db.query(CombatAction).filter(CombatAction.turn_id == current_turn.id).first()
        is not None
        or db.query(CombatTacticalAction)
        .filter(CombatTacticalAction.turn_id == current_turn.id)
        .first()
        is not None
    ):
        raise CombatTacticalActionError("Current turn already has a resolved action.")

    action_cost = _encumbrance_adjusted_action_cost(db, actor, action_type)
    cost = (
        validate_resource_cost(
            db,
            actor,
            CharacterResourceKey.STAMINA,
            action_cost,
        )
        if action_cost > 0
        else None
    )
    previous_range: str | None = None
    new_range: str | None = None
    roll_raw: int | None = None
    modifier: int | None = None
    total: int | None = None
    dc: int | None = None
    success = True
    if action_type in {
        CombatTacticalActionType.APPROACH,
        CombatTacticalActionType.RETREAT,
        CombatTacticalActionType.DISENGAGE,
    }:
        previous_range = target.range_band
        new_range = _next_range(action_type, CombatRangeBand(target.range_band)).value
    elif action_type == CombatTacticalActionType.FLEE:
        modifier = _agility_modifier(db, actor)
        result = d20(modifier, rng)
        roll_raw = result.raw
        total = result.total
        dc = FLEE_DC
        success = result.raw == 20 or (result.raw != 1 and result.total >= dc)

    action = CombatTacticalAction(
        encounter_id=encounter.id,
        turn_id=current_turn.id,
        actor_participant_id=actor.id,
        target_participant_id=target.id if target else None,
        action_key=normalized_key,
        action_type=action_type.value,
        previous_range_band=previous_range,
        new_range_band=new_range,
        roll=roll_raw,
        modifier=modifier,
        total=total,
        dc=dc,
        success=success,
        created_world_minute=get_world_time(db, encounter.campaign_id).total_minutes(),
    )
    db.add(action)
    db.flush()
    if cost is not None:
        apply_action_cost(db, encounter, action, actor, cost)
    if new_range is not None:
        target.range_band = new_range
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_TACTICAL_ACTION_RESOLVED,
        actor_type=actor.actor_type.lower(),
        actor_id=actor.actor_id,
        payload={
            "encounter_id": encounter.id,
            "action_id": action.id,
            "action_type": action_type.value,
            "actor_participant_id": actor.id,
            "target_participant_id": target.id if target else None,
            "previous_range_band": previous_range,
            "new_range_band": new_range,
            "roll": roll_raw,
            "modifier": modifier,
            "total": total,
            "dc": dc,
            "success": success,
            "resource_cost": action.resource_cost,
        },
    )

    should_end = action_type == CombatTacticalActionType.FLEE and success and (
        actor.actor_type == CombatActorType.CHARACTER.value
        or _remaining_side_count(db, encounter.id, excluding=actor.id) <= 1
    )
    complete_current_turn(
        db,
        encounter,
        actor,
        completion_key=normalized_key,
        advance=not should_end,
    )
    condition = None
    if action_type in _DEFENSIVE_CONDITIONS:
        condition = apply_condition(
            db,
            encounter,
            actor,
            condition_type=_DEFENSIVE_CONDITIONS[action_type],
            duration_turns=1,
            application_key=f"tactical:{action.id}",
            source_tactical_action=action,
        ).condition
    elif action_type == CombatTacticalActionType.FLEE and success:
        remove_participant(db, encounter, actor, reason=f"flee:{action.id}")
        if should_end:
            end_encounter(
                db,
                encounter,
                (
                    CombatEncounterStatus.FLED
                    if actor.actor_type == CombatActorType.CHARACTER.value
                    else CombatEncounterStatus.VICTORY
                ),
                reason=f"flee:{actor.side_key}",
            )
    db.flush()
    return TacticalActionResolution(action, condition)


def _validate_actor_and_target(
    encounter: CombatEncounter,
    actor: CombatParticipant,
    target: CombatParticipant | None,
    action_type: CombatTacticalActionType,
) -> None:
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        raise CombatTacticalActionError("Combat encounter is not active.")
    if actor.encounter_id != encounter.id or not actor.active:
        raise CombatTacticalActionError("Tactical actor must be active in encounter.")
    requires_target = action_type in {
        CombatTacticalActionType.APPROACH,
        CombatTacticalActionType.RETREAT,
        CombatTacticalActionType.DISENGAGE,
    }
    if requires_target:
        if target is None:
            raise CombatTacticalActionError("Tactical movement requires a target.")
        if target.encounter_id != encounter.id or not target.active:
            raise CombatTacticalActionError("Tactical target must be active in encounter.")
        if target.id == actor.id or target.side_key == actor.side_key:
            raise CombatTacticalActionError("Tactical movement requires an opposing target.")
    elif target is not None:
        raise CombatTacticalActionError("This tactical action does not accept a target.")


def _next_range(
    action_type: CombatTacticalActionType,
    current: CombatRangeBand,
) -> CombatRangeBand:
    if action_type == CombatTacticalActionType.APPROACH:
        mapping = {
            CombatRangeBand.OUT_OF_REACH: CombatRangeBand.FAR,
            CombatRangeBand.FAR: CombatRangeBand.NEAR,
            CombatRangeBand.NEAR: CombatRangeBand.ENGAGED,
        }
        if current not in mapping:
            raise CombatTacticalActionError("Target is already engaged.")
        return mapping[current]
    if action_type == CombatTacticalActionType.DISENGAGE:
        if current != CombatRangeBand.ENGAGED:
            raise CombatTacticalActionError("Disengage requires an engaged target.")
        return CombatRangeBand.NEAR
    mapping = {
        CombatRangeBand.ENGAGED: CombatRangeBand.NEAR,
        CombatRangeBand.NEAR: CombatRangeBand.FAR,
        CombatRangeBand.FAR: CombatRangeBand.OUT_OF_REACH,
    }
    if current not in mapping:
        raise CombatTacticalActionError("Target is already out of reach.")
    return mapping[current]


def _agility_modifier(db: Session, participant: CombatParticipant) -> int:
    if participant.actor_type != CombatActorType.CHARACTER.value:
        return 0
    character = db.get(Character, participant.actor_id)
    if character is None:
        raise CombatTacticalActionError("Fleeing character does not exist.")
    agility = get_character_attribute(
        db,
        character.id,
        CharacterAttributeKey.AGILITY,
    )
    encumbrance = get_character_encumbrance(db, character.id)
    return attribute_check_modifier(agility.value) - encumbrance.agility_penalty


def _encumbrance_adjusted_action_cost(
    db: Session,
    participant: CombatParticipant,
    action_type: CombatTacticalActionType,
) -> float:
    base_cost = _ACTION_COSTS[action_type]
    if base_cost == 0 or participant.actor_type != CombatActorType.CHARACTER.value:
        return base_cost
    encumbrance = get_character_encumbrance(db, participant.actor_id)
    return round(base_cost * encumbrance.stamina_multiplier, 1)


def _remaining_side_count(
    db: Session,
    encounter_id: str,
    *,
    excluding: str,
) -> int:
    return len(
        {
            row.side_key
            for row in list_active_participants(db, encounter_id)
            if row.id != excluding
        }
    )
