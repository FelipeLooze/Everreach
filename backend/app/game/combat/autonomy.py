import random
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActionType,
    CombatActorType,
    CombatDecisionKind,
    CombatEncounterStatus,
    CombatRangeBand,
    CombatTacticalActionType,
    EventType,
    RiskTolerance,
)
from app.db.models.combat import (
    CombatAction,
    CombatAutonomousDecision,
    CombatEncounter,
    CombatParticipant,
    CombatTacticalAction,
)
from app.db.models.character import Character
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.simulated_player import SimulatedPlayerSkill
from app.game.combat.actions import resolve_attack
from app.game.combat.encounters import list_active_participants
from app.game.combat.tactics import resolve_tactical_action
from app.game.combat.turns import get_current_turn
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


_DECISION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")
_FLEE_HP_THRESHOLDS = {
    RiskTolerance.CAUTIOUS.value: 0.5,
    RiskTolerance.BALANCED.value: 0.3,
    RiskTolerance.BOLD.value: 0.15,
}
_RANGE_PRIORITY = {
    CombatRangeBand.ENGAGED.value: 0,
    CombatRangeBand.NEAR.value: 1,
    CombatRangeBand.FAR.value: 2,
    CombatRangeBand.OUT_OF_REACH.value: 3,
}


class CombatAutonomyError(ValueError):
    pass


@dataclass(frozen=True)
class AutonomousCombatResolution:
    decision: CombatAutonomousDecision
    combat_action: CombatAction | None = None
    tactical_action: CombatTacticalAction | None = None
    replayed: bool = False


@dataclass(frozen=True)
class _Choice:
    kind: CombatDecisionKind
    action_type: CombatActionType | CombatTacticalActionType
    reason: str
    target: CombatParticipant | None


def resolve_autonomous_turn(
    db: Session,
    encounter: CombatEncounter,
    *,
    decision_key: str,
    rng: random.Random | None = None,
) -> AutonomousCombatResolution:
    """Choose and resolve one NPC or transported-player turn without an LLM."""
    normalized_key = decision_key.strip().lower()
    if not _DECISION_KEY_PATTERN.fullmatch(normalized_key):
        raise CombatAutonomyError("Invalid autonomous decision key.")
    existing = (
        db.query(CombatAutonomousDecision)
        .filter(
            CombatAutonomousDecision.encounter_id == encounter.id,
            CombatAutonomousDecision.decision_key == normalized_key,
        )
        .one_or_none()
    )
    if existing is not None:
        return AutonomousCombatResolution(
            existing,
            existing.combat_action,
            existing.tactical_action,
            replayed=True,
        )

    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        raise CombatAutonomyError("Combat encounter is not active.")
    turn = get_current_turn(db, encounter)
    if turn is None:
        raise CombatAutonomyError("Initiative has not been rolled.")
    actor = turn.participant
    if actor.actor_type == CombatActorType.CHARACTER.value:
        raise CombatAutonomyError("The protagonist requires a player decision.")
    if actor.actor_type not in {
        CombatActorType.NPC.value,
        CombatActorType.SIMULATED_PLAYER.value,
    }:
        raise CombatAutonomyError("Unsupported autonomous combat actor.")

    actor_state = _actor_state(db, actor)
    risk_tolerance = _risk_tolerance(actor_state)
    hp_ratio = _ratio(actor_state.hp_current, actor_state.hp_max)
    stamina_ratio = _ratio(actor_state.stamina_current, actor_state.stamina_max)
    target = _select_target(db, encounter, actor)
    choice = _choose_action(
        target,
        hp_ratio=hp_ratio,
        stamina=float(actor_state.stamina_current),
        risk_tolerance=risk_tolerance,
        can_use_ranged=_has_ranged_capability(db, actor, actor_state),
    )
    action_key = f"auto:{normalized_key}"
    combat_action = None
    tactical_action = None
    if choice.kind == CombatDecisionKind.ATTACK:
        combat_action = resolve_attack(
            db,
            encounter,
            actor,
            choice.target,
            action_type=choice.action_type,
            action_key=action_key,
            rng=rng,
        ).action
    else:
        tactical_action = resolve_tactical_action(
            db,
            encounter,
            actor,
            target=choice.target if _requires_target(choice.action_type) else None,
            action_type=choice.action_type,
            action_key=action_key,
            rng=rng,
        ).action

    decision = CombatAutonomousDecision(
        encounter_id=encounter.id,
        turn_id=turn.id,
        actor_participant_id=actor.id,
        target_participant_id=choice.target.id if choice.target else None,
        combat_action_id=combat_action.id if combat_action else None,
        tactical_action_id=tactical_action.id if tactical_action else None,
        decision_key=normalized_key,
        decision_kind=choice.kind.value,
        action_type=choice.action_type.value,
        reason=choice.reason,
        risk_tolerance=risk_tolerance,
        hp_ratio=hp_ratio,
        stamina_ratio=stamina_ratio,
        created_world_minute=get_world_time(db, encounter.campaign_id).total_minutes(),
    )
    db.add(decision)
    db.flush()
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_AUTONOMOUS_DECISION_RESOLVED,
        actor_type=actor.actor_type.lower(),
        actor_id=actor.actor_id,
        payload={
            "encounter_id": encounter.id,
            "turn_id": turn.id,
            "decision_id": decision.id,
            "decision_kind": decision.decision_kind,
            "action_type": decision.action_type,
            "reason": decision.reason,
            "risk_tolerance": decision.risk_tolerance,
            "hp_ratio": decision.hp_ratio,
            "stamina_ratio": decision.stamina_ratio,
            "target_participant_id": decision.target_participant_id,
            "combat_action_id": decision.combat_action_id,
            "tactical_action_id": decision.tactical_action_id,
        },
    )
    db.flush()
    return AutonomousCombatResolution(decision, combat_action, tactical_action)


def resolve_until_player_turn(
    db: Session,
    encounter: CombatEncounter,
    *,
    decision_key_prefix: str,
    rng: random.Random | None = None,
    max_turns: int = 32,
) -> list[AutonomousCombatResolution]:
    """Resolve consecutive autonomous turns and stop before protagonist authority."""
    normalized_prefix = decision_key_prefix.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,39}", normalized_prefix):
        raise CombatAutonomyError("Invalid autonomous decision key prefix.")
    if max_turns < 1 or max_turns > 100:
        raise CombatAutonomyError("Autonomous turn limit must be between 1 and 100.")

    results: list[AutonomousCombatResolution] = []
    while (
        encounter.status == CombatEncounterStatus.ACTIVE.value
        and len(results) < max_turns
    ):
        turn = get_current_turn(db, encounter)
        if turn is None or turn.participant.actor_type == CombatActorType.CHARACTER.value:
            break
        results.append(
            resolve_autonomous_turn(
                db,
                encounter,
                decision_key=f"{normalized_prefix}:{turn.id}",
                rng=rng,
            )
        )
    return results


def _choose_action(
    target: CombatParticipant,
    *,
    hp_ratio: float,
    stamina: float,
    risk_tolerance: str,
    can_use_ranged: bool = False,
) -> _Choice:
    if hp_ratio <= _FLEE_HP_THRESHOLDS[risk_tolerance]:
        if stamina >= 2:
            return _Choice(
                CombatDecisionKind.TACTICAL,
                CombatTacticalActionType.FLEE,
                "LOW_HEALTH_FLEE",
                None,
            )
        if stamina >= 1:
            return _Choice(
                CombatDecisionKind.TACTICAL,
                CombatTacticalActionType.GUARD,
                "LOW_HEALTH_DEFEND",
                None,
            )
        return _wait_choice("LOW_HEALTH_EXHAUSTED")

    target_range = CombatRangeBand(target.range_band)
    if target_range == CombatRangeBand.ENGAGED:
        if stamina >= 2:
            return _Choice(
                CombatDecisionKind.ATTACK,
                CombatActionType.MELEE_ATTACK,
                "ENGAGED_ATTACK",
                target,
            )
        if stamina >= 1:
            return _Choice(
                CombatDecisionKind.TACTICAL,
                CombatTacticalActionType.GUARD,
                "CONSERVE_STAMINA",
                None,
            )
        return _wait_choice("EXHAUSTED")
    if target_range in {CombatRangeBand.NEAR, CombatRangeBand.FAR}:
        if can_use_ranged and stamina >= 1:
            return _Choice(
                CombatDecisionKind.ATTACK,
                CombatActionType.RANGED_ATTACK,
                "RANGED_OPPORTUNITY",
                target,
            )
        if stamina >= 1:
            return _Choice(
                CombatDecisionKind.TACTICAL,
                CombatTacticalActionType.APPROACH,
                "CLOSE_FOR_MELEE",
                target,
            )
        return _wait_choice("EXHAUSTED")
    if stamina >= 1:
        return _Choice(
            CombatDecisionKind.TACTICAL,
            CombatTacticalActionType.APPROACH,
            "TARGET_OUT_OF_REACH",
            target,
        )
    return _wait_choice("EXHAUSTED")


def _select_target(
    db: Session,
    encounter: CombatEncounter,
    actor: CombatParticipant,
) -> CombatParticipant:
    opponents = [
        row
        for row in list_active_participants(db, encounter.id)
        if row.side_key != actor.side_key and row.id != actor.id
    ]
    if not opponents:
        raise CombatAutonomyError("Autonomous actor has no active opponent.")
    return min(
        opponents,
        key=lambda row: (
            _RANGE_PRIORITY[row.range_band],
            _target_hp_ratio(db, row),
            row.id,
        ),
    )


def _target_hp_ratio(db: Session, participant: CombatParticipant) -> float:
    actor = _actor_state(db, participant)
    return _ratio(actor.hp_current, actor.hp_max)


def _actor_state(
    db: Session,
    participant: CombatParticipant,
) -> Character | NPC | SimulatedPlayer:
    model = {
        CombatActorType.CHARACTER.value: Character,
        CombatActorType.NPC.value: NPC,
        CombatActorType.SIMULATED_PLAYER.value: SimulatedPlayer,
    }.get(participant.actor_type)
    actor = db.get(model, participant.actor_id) if model is not None else None
    if actor is None:
        raise CombatAutonomyError("Autonomous combat actor does not exist.")
    return actor


def _risk_tolerance(actor: NPC | SimulatedPlayer) -> str:
    value = getattr(actor, "risk_tolerance", RiskTolerance.BALANCED.value)
    return value if value in _FLEE_HP_THRESHOLDS else RiskTolerance.BALANCED.value


def _has_ranged_capability(
    db: Session,
    participant: CombatParticipant,
    actor: NPC | SimulatedPlayer,
) -> bool:
    markers = ("archer", "hunter", "ranger", "bow", "crossbow", "arco", "besta", "tiro")
    if participant.actor_type == CombatActorType.NPC.value:
        role = actor.role.lower()
        return any(marker in role for marker in markers)
    skill_names = (
        db.query(SimulatedPlayerSkill.name)
        .filter(SimulatedPlayerSkill.simulated_player_id == actor.id)
        .all()
    )
    return any(
        marker in name.lower()
        for (name,) in skill_names
        for marker in markers
    )


def _ratio(current: float, maximum: float) -> float:
    return max(0.0, min(1.0, float(current) / float(maximum))) if maximum > 0 else 0.0


def _requires_target(
    action_type: CombatActionType | CombatTacticalActionType,
) -> bool:
    return action_type in {
        CombatTacticalActionType.APPROACH,
        CombatTacticalActionType.RETREAT,
        CombatTacticalActionType.DISENGAGE,
    }


def _wait_choice(reason: str) -> _Choice:
    return _Choice(
        CombatDecisionKind.TACTICAL,
        CombatTacticalActionType.WAIT,
        reason,
        None,
    )
