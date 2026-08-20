import random

from sqlalchemy.orm import Session
from app.simulation.results import WorldTickResult
from app.simulation import (
    arrival_simulation,
    development_simulation,
    group_simulation,
    knowledge_simulation,
    npc_simulation,
    player_simulation,
)
from app.simulation.scope import build_simulation_scope


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

    # Arrivals may change abstract population, so scope is captured afterward.
    scope = build_simulation_scope(db, campaign_id)

    group_result = group_simulation.tick(
        db,
        campaign_id,
        minutes,
    )

    player_result = player_simulation.tick(
        db,
        campaign_id,
        minutes,
        rng=rng,
        scope=scope,
    )

    npc_result = npc_simulation.tick(
        db,
        campaign_id,
        minutes,
        scope=scope,
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
        scope=scope,
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
        simulated_player_groups_formed=group_result.groups_formed,
        npc_changes=npc_result.changes,
        world_development_changes=development_result.changes,
        knowledge_social_opportunities=(
            knowledge_result.opportunities
        ),
        knowledge_propagations=(
            knowledge_result.propagations
        ),
        detailed_locations=len(scope.detailed_location_ids),
        materialized_simulated_players=(
            scope.materialized_simulated_players
        ),
        abstract_simulated_players=(
            scope.abstract_simulated_players
        ),
    )
