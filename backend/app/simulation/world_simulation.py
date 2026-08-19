import random

from sqlalchemy.orm import Session
from app.simulation.results import WorldTickResult
from app.simulation import (
    arrival_simulation,
    development_simulation,
    knowledge_simulation,
    npc_simulation,
    player_simulation,
)


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
    rng: random.Random | None = None,
) -> WorldTickResult:
    """Advance autonomous world systems after the world clock moves forward."""

    if minutes <= 0:
        return WorldTickResult()

    arrival_result = arrival_simulation.tick(
        db,
        campaign_id,
        minutes,
    )

    player_result = player_simulation.tick(
        db,
        campaign_id,
        minutes,
        rng=rng,
    )

    npc_result = npc_simulation.tick(
        db,
        campaign_id,
        minutes,
    )

    development_result = development_simulation.tick(
        db,
        campaign_id,
        minutes,
    )

    knowledge_result = knowledge_simulation.tick(
        db,
        campaign_id,
        minutes,
    )

    return WorldTickResult(
        simulated_player_arrivals=(
            arrival_result.arrivals
        ),
        simulated_player_travel_started=(
            player_result.travel_started
        ),
        simulated_player_moves=player_result.moved,
        simulated_player_training=player_result.trained,
        npc_changes=npc_result.changes,
        world_development_changes=development_result.changes,
        knowledge_social_opportunities=(
            knowledge_result.opportunities
        ),
        knowledge_propagations=(
            knowledge_result.propagations
        ),
    )