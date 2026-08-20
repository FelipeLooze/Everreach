from sqlalchemy.orm import Session

from app.core.enums import EventType, SimulatedPlayerArchetype, SimulatedPlayerGoalType
from app.db.models.location import Location
from app.db.models.simulated_player import SimulatedPlayer
from app.services.event_log import log_event


def assign_next_goal(
    db: Session,
    player: SimulatedPlayer,
    *,
    occurred_world_minute: int,
    previous_goal_type: str | None = None,
) -> None:
    location = db.get(Location, player.location_id)

    if player.archetype == SimulatedPlayerArchetype.TRAINER.value:
        goal_type = SimulatedPlayerGoalType.TRAIN_SELF
        subject = f"level:{player.level + 1}"
        description = f"Alcançar o Level {player.level + 1} por meio de treino consistente."
    elif player.archetype == SimulatedPlayerArchetype.SOCIAL.value:
        goal_type = SimulatedPlayerGoalType.GATHER_KNOWLEDGE
        subject = f"location:{player.location_id}"
        description = "Descobrir uma informação nova com as pessoas deste lugar."
    elif player.archetype == SimulatedPlayerArchetype.ADVENTURER.value:
        goal_type = SimulatedPlayerGoalType.SEEK_DANGER
        subject = "danger:3"
        description = "Percorrer uma rota perigosa e sobreviver à viagem."
    else:
        if previous_goal_type == SimulatedPlayerGoalType.EXPLORE_REGION.value:
            goal_type = SimulatedPlayerGoalType.GATHER_KNOWLEDGE
            subject = f"location:{player.location_id}"
            description = "Reunir informações que indiquem uma nova fronteira."
        else:
            goal_type = SimulatedPlayerGoalType.EXPLORE_REGION
            subject = f"region:{location.region_id}" if location else None
            description = "Explorar locais ainda não visitados nesta região."

    player.goal_type = goal_type.value
    player.goal_subject = subject
    player.goal = description
    log_event(
        db,
        player.campaign_id,
        EventType.SIMULATED_PLAYER_GOAL_ASSIGNED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={
            "goal_type": player.goal_type,
            "goal_subject": player.goal_subject,
            "goal": player.goal,
        },
        occurred_world_minute=occurred_world_minute,
    )


def complete_goal(
    db: Session,
    player: SimulatedPlayer,
    *,
    occurred_world_minute: int,
) -> None:
    completed_type = player.goal_type
    completed_subject = player.goal_subject
    completed_description = player.goal
    player.goal_type = SimulatedPlayerGoalType.NONE.value
    player.goal_subject = None
    log_event(
        db,
        player.campaign_id,
        EventType.SIMULATED_PLAYER_GOAL_COMPLETED,
        actor_type="simulated_player",
        actor_id=player.id,
        payload={
            "goal_type": completed_type,
            "goal_subject": completed_subject,
            "goal": completed_description,
        },
        occurred_world_minute=occurred_world_minute,
    )
    assign_next_goal(
        db,
        player,
        occurred_world_minute=occurred_world_minute,
        previous_goal_type=completed_type,
    )
