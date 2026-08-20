from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    CharacterResourceKey,
    CombatActionType,
    CombatActorType,
    EventType,
)
from app.db.models.character import Character
from app.db.models.combat import CombatAction, CombatEncounter, CombatParticipant
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.services.event_log import log_event


_ACTION_COSTS = {
    CombatActionType.MELEE_ATTACK: (CharacterResourceKey.STAMINA, 2.0),
    CombatActionType.RANGED_ATTACK: (CharacterResourceKey.STAMINA, 1.0),
}


class CombatResourceError(ValueError):
    pass


@dataclass(frozen=True)
class CombatResourceCost:
    resource_key: CharacterResourceKey
    amount: float
    before: float


def validate_action_cost(
    db: Session,
    participant: CombatParticipant,
    action_type: CombatActionType,
) -> CombatResourceCost:
    if not isinstance(action_type, CombatActionType):
        raise CombatResourceError("Invalid combat action type for resource cost.")
    resource_key, amount = _ACTION_COSTS[action_type]
    actor = _actor(db, participant)
    before = float(getattr(actor, f"{resource_key.value.lower()}_current"))
    if before < amount:
        raise CombatResourceError(
            f"Insufficient {resource_key.value.lower()} for combat action."
        )
    return CombatResourceCost(resource_key, amount, before)


def apply_action_cost(
    db: Session,
    encounter: CombatEncounter,
    action: CombatAction,
    participant: CombatParticipant,
    cost: CombatResourceCost,
) -> CombatAction:
    """Deduct one validated action cost once and persist its exact resource snapshot."""
    if action.resource_cost is not None:
        return action
    if action.encounter_id != encounter.id or action.actor_participant_id != participant.id:
        raise CombatResourceError("Resource cost does not match combat action.")
    actor = _actor(db, participant)
    field = f"{cost.resource_key.value.lower()}_current"
    before = float(getattr(actor, field))
    if before < cost.amount:
        raise CombatResourceError(
            f"Insufficient {cost.resource_key.value.lower()} for combat action."
        )
    after = before - cost.amount
    setattr(actor, field, after)
    action.resource_key = cost.resource_key.value
    action.resource_cost = cost.amount
    action.resource_before = before
    action.resource_after = after
    log_event(
        db,
        encounter.campaign_id,
        EventType.COMBAT_RESOURCE_SPENT,
        actor_type=participant.actor_type.lower(),
        actor_id=participant.actor_id,
        payload={
            "encounter_id": encounter.id,
            "action_id": action.id,
            "participant_id": participant.id,
            "resource_key": cost.resource_key.value,
            "cost": cost.amount,
            "before": before,
            "after": after,
        },
    )
    db.flush()
    return action


def _actor(
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
        raise CombatResourceError("Combat resource owner does not exist.")
    return actor
