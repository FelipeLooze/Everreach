from sqlalchemy.orm import Session

from app.game.time.clock import get_world_time
from app.simulation.cadence import (
    boundary_minutes_crossed,
)
from app.simulation.results import KnowledgeSimulationResult


SOCIAL_INTERVAL_MINUTES = 24 * 60


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> KnowledgeSimulationResult:
    if minutes <= 0:
        return KnowledgeSimulationResult()

    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    opportunity_world_minutes = (
        boundary_minutes_crossed(
            current_world_minute,
            minutes,
            SOCIAL_INTERVAL_MINUTES,
        )
    )

    return KnowledgeSimulationResult(
        opportunities=len(
            opportunity_world_minutes
        ),
        resolvable_opportunities=(
            1
            if opportunity_world_minutes
            else 0
        ),
        opportunity_world_minutes=(
            opportunity_world_minutes
        ),
    )