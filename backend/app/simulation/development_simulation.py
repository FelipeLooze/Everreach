from sqlalchemy.orm import Session

from app.core.enums import WorldDevelopmentStatus
from app.db.models.world_development import WorldDevelopment
from app.game.time.clock import get_world_time
from app.simulation.results import (
    WorldDevelopmentSimulationResult,
)


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


def process_development(
    db: Session,
    development: WorldDevelopment,
    current_world_minute: int,
) -> bool:
    """
    Process one due world development.

    Development-specific mechanics will be added later.
    Returning True means persistent mechanical state changed.
    """

    return False


def tick(
    db: Session,
    campaign_id: str,
    minutes: int,
) -> WorldDevelopmentSimulationResult:
    if minutes <= 0:
        return WorldDevelopmentSimulationResult()

    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    changes = 0

    for development in due_developments(
        db,
        campaign_id,
    ):
        changed = process_development(
            db,
            development,
            current_world_minute,
        )

        if changed:
            changes += 1

    return WorldDevelopmentSimulationResult(
        changes=changes,
    )