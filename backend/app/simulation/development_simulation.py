import json
import math
from sqlalchemy.orm import Session
from app.services.event_log import log_event
from app.simulation.results import WorldDevelopmentSimulationResult
from app.db.models.world_development import WorldDevelopment
from app.game.time.clock import get_world_time
from app.simulation.cadence import scheduled_occurrences_due
from app.game.developments.knowledge import (
    create_development_event_fact,
)
from app.core.enums import (
    EventType,
    WorldDevelopmentStatus,
    WorldDevelopmentType,
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


def _process_construction(
    db: Session,
    development: WorldDevelopment,
    current_world_minute: int,
) -> bool:
    payload = json.loads(development.payload_json)

    interval_minutes = int(
        payload["interval_minutes"]
    )
    progress = int(
        payload.get("progress", 0)
    )
    progress_per_update = int(
        payload["progress_per_update"]
    )

    if progress >= 100:
        development.status = (
            WorldDevelopmentStatus.COMPLETED.value
        )
        development.next_update_world_minute = None
        return True

    if progress_per_update <= 0:
        raise ValueError(
            "progress_per_update must be greater than zero"
        )

    occurrences_due = scheduled_occurrences_due(
        current_world_minute=current_world_minute,
        next_update_world_minute=(
            development.next_update_world_minute
        ),
        interval_minutes=interval_minutes,
    )

    if occurrences_due <= 0:
        return False

    updates_needed = math.ceil(
        (100 - progress)
        / progress_per_update
    )

    applied_updates = min(
        occurrences_due,
        updates_needed,
    )

    first_due_world_minute = (
        development.next_update_world_minute
    )

    for update_index in range(applied_updates):
        previous_progress = min(
            100,
            progress
            + update_index * progress_per_update,
        )

        update_progress = min(
            100,
            progress
            + (update_index + 1) * progress_per_update,
        )

        occurred_world_minute = (
            first_due_world_minute
            + update_index * interval_minutes
        )

        completed = update_progress >= 100

        event = log_event(
            db,
            development.campaign_id,
            (
                EventType.WORLD_DEVELOPMENT_COMPLETED
                if completed
                else EventType.WORLD_DEVELOPMENT_UPDATED
            ),
            actor_type="world_development",
            actor_id=development.id,
            payload={
                "development_id": development.id,
                "development_type": (
                    development.development_type
                ),
                "title": development.title,
                "region_id": development.region_id,
                "location_id": development.location_id,
                "previous_progress": previous_progress,
                "progress": update_progress,
            },
            occurred_world_minute=occurred_world_minute,
        )

        create_development_event_fact(
            db,
            event,
        )
    progress = min(
        100,
        progress
        + applied_updates * progress_per_update,
    )

    last_processed_world_minute = (
        first_due_world_minute
        + (applied_updates - 1) * interval_minutes
    )

    payload["progress"] = progress

    development.payload_json = json.dumps(payload)
    development.last_updated_world_minute = (
        last_processed_world_minute
    )

    if progress >= 100:
        development.status = (
            WorldDevelopmentStatus.COMPLETED.value
        )
        development.next_update_world_minute = None
    else:
        development.next_update_world_minute = (
            first_due_world_minute
            + applied_updates * interval_minutes
        )

    return True


def process_development(
    db: Session,
    development: WorldDevelopment,
    current_world_minute: int,
) -> bool:
    if (
        development.development_type
        == WorldDevelopmentType.CONSTRUCTION.value
    ):
        return _process_construction(
            db,
            development,
            current_world_minute,
        )

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