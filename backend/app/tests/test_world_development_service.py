import json

import pytest

from app.core.enums import (
    WorldDevelopmentStatus,
    WorldDevelopmentType,
)
from app.game.developments.service import (
    create_world_development,
)
from app.game.time.clock import get_world_time
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)


def test_create_world_development_sets_schedule(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Service",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    interval = 7 * 24 * 60

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Nova ponte",
        interval_minutes=interval,
        payload={
            "progress": 0,
            "progress_per_update": 10,
        },
        location_id=village.id,
        description="Uma ponte está sendo construída.",
    )

    payload = json.loads(
        development.payload_json
    )

    assert development.campaign_id == campaign.id
    assert development.region_id == region.id
    assert development.location_id == village.id

    assert (
        development.development_type
        == WorldDevelopmentType.CONSTRUCTION.value
    )

    assert (
        development.status
        == WorldDevelopmentStatus.ACTIVE.value
    )

    assert development.started_world_minute == now
    assert development.last_updated_world_minute is None

    assert (
        development.next_update_world_minute
        == now + interval
    )

    assert payload == {
        "progress": 0,
        "progress_per_update": 10,
        "interval_minutes": interval,
    }


def test_create_world_development_rejects_invalid_interval(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Invalid Development",
    )

    with pytest.raises(
        ValueError,
        match="interval_minutes",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção inválida",
            interval_minutes=0,
        )


def test_create_world_development_rejects_location_from_other_campaign(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Campaign A",
    )

    other_campaign = create_campaign(
        db_session,
        "Campaign B",
    )

    _other_region, other_location = (
        seed_initial_region(
            db_session,
            other_campaign.id,
        )
    )

    with pytest.raises(
        ValueError,
        match="location does not belong to campaign",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção impossível",
            interval_minutes=7 * 24 * 60,
            location_id=other_location.id,
        )

def test_create_construction_defaults_progress_to_zero(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Construction Defaults",
    )

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Nova construção",
        interval_minutes=7 * 24 * 60,
        payload={
            "progress_per_update": 10,
        },
    )

    payload = json.loads(
        development.payload_json
    )

    assert payload["progress"] == 0
    assert payload["progress_per_update"] == 10


def test_create_construction_rejects_invalid_progress(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Invalid Construction Progress",
    )

    with pytest.raises(
        ValueError,
        match="progress must be between 0 and 100",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção inválida",
            interval_minutes=7 * 24 * 60,
            payload={
                "progress": 120,
                "progress_per_update": 10,
            },
        )


def test_create_construction_requires_positive_progress_per_update(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Invalid Construction Rate",
    )

    with pytest.raises(
        ValueError,
        match="progress_per_update",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção sem ritmo",
            interval_minutes=7 * 24 * 60,
            payload={
                "progress": 0,
            },
        )

def test_create_construction_rejects_already_completed_progress(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Completed Construction",
    )

    with pytest.raises(
        ValueError,
        match="active construction progress must be below 100",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção já pronta",
            interval_minutes=7 * 24 * 60,
            payload={
                "progress": 100,
                "progress_per_update": 10,
            },
        )