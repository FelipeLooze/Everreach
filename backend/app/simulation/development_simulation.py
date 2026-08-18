from sqlalchemy.orm import Session
from app.simulation.results import (
    WorldDevelopmentSimulationResult,
)
from app.core.enums import WorldDevelopmentStatus
from app.db.models.world_development import WorldDevelopment
from app.game.time.clock import get_world_time


def due_developments(
    db: Session,
    campaign_id: str,
) -> list[WorldDevelopment]:
    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    return (
        db.query(WorldDevelopment)
        .filter(
            WorldDevelopment.campaign_id == campaign_id,
            WorldDevelopment.status
            == WorldDevelopmentStatus.ACTIVE.value,
            WorldDevelopment.next_update_world_minute.is_not(
                None
            ),
            WorldDevelopment.next_update_world_minute
            <= current_world_minute,
        )
        .order_by(
            WorldDevelopment.next_update_world_minute,
            WorldDevelopment.id,
        )
        .all()
    )

def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> WorldDevelopmentSimulationResult:
    """
    Advance persistent world developments.

    Mechanical development progression will be added
    incrementally. For now this establishes the World Tick
    subsystem contract without changing world state.
    """

    if minutes <= 0:
        return WorldDevelopmentSimulationResult()

    return WorldDevelopmentSimulationResult()