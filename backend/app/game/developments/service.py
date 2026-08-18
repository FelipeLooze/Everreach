import json

from app.core.enums import (
    EventType,
    WorldDevelopmentStatus,
    WorldDevelopmentType,
)
from sqlalchemy.orm import Session
from app.db.models.campaign import Campaign
from app.db.models.location import Location
from app.db.models.region import Region
from app.db.models.world_development import WorldDevelopment
from app.game.time.clock import get_world_time
from app.services.event_log import log_event

def create_world_development(
    db: Session,
    campaign_id: str,
    development_type: WorldDevelopmentType,
    title: str,
    *,
    interval_minutes: int,
    payload: dict | None = None,
    region_id: str | None = None,
    location_id: str | None = None,
    description: str = "",
) -> WorldDevelopment:
    campaign = db.get(
        Campaign,
        campaign_id,
    )

    if campaign is None:
        raise ValueError(
            "campaign not found"
        )

    if interval_minutes <= 0:
        raise ValueError(
            "interval_minutes must be greater than zero"
        )

    region = None

    if region_id is not None:
        region = db.get(
            Region,
            region_id,
        )

        if (
            region is None
            or region.campaign_id != campaign_id
        ):
            raise ValueError(
                "region does not belong to campaign"
            )

    if location_id is not None:
        location = db.get(
            Location,
            location_id,
        )

        if location is None:
            raise ValueError(
                "location not found"
            )

        location_region = db.get(
            Region,
            location.region_id,
        )

        if (
            location_region is None
            or location_region.campaign_id
            != campaign_id
        ):
            raise ValueError(
                "location does not belong to campaign"
            )

        if (
            region is not None
            and location.region_id != region.id
        ):
            raise ValueError(
                "location does not belong to region"
            )

        if region is None:
            region_id = location.region_id

    current_world_minute = get_world_time(
        db,
        campaign_id,
    ).total_minutes()

    development_payload = dict(
        payload or {}
    )

    if development_type == WorldDevelopmentType.CONSTRUCTION:
        progress = int(
            development_payload.get(
                "progress",
                0,
            )
        )

        progress_per_update = int(
            development_payload.get(
                "progress_per_update",
                0,
            )
        )

        if progress < 0 or progress > 100:
            raise ValueError(
                "progress must be between 0 and 100"
            )

        if progress == 100:
            raise ValueError(
                "active construction progress must be below 100"
            )

        if progress_per_update <= 0:
            raise ValueError(
                "progress_per_update must be greater than zero"
            )

        development_payload["progress"] = progress
        development_payload[
            "progress_per_update"
        ] = progress_per_update

    development_payload[
        "interval_minutes"
    ] = interval_minutes

    development = WorldDevelopment(
        campaign_id=campaign_id,
        region_id=region_id,
        location_id=location_id,
        development_type=development_type.value,
        status=WorldDevelopmentStatus.ACTIVE.value,
        title=title,
        description=description,
        started_world_minute=current_world_minute,
        last_updated_world_minute=None,
        next_update_world_minute=(
            current_world_minute
            + interval_minutes
        ),
        payload_json=json.dumps(
            development_payload
        ),
    )

    db.add(development)
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.WORLD_DEVELOPMENT_CREATED,
        actor_type="world_development",
        actor_id=development.id,
        payload={
            "development_id": development.id,
            "development_type": development.development_type,
            "title": development.title,
            "region_id": development.region_id,
            "location_id": development.location_id,
            "status": development.status,
        },
        occurred_world_minute=current_world_minute,
    )

    return development