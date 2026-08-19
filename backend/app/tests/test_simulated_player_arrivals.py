import json

import pytest

from app.core.enums import EventType
from app.db.models.event import WorldEvent
from app.game.players.service import (
    abstract_simulated_player_count_at_location,
    register_simulated_player_world_arrival,
    set_abstract_simulated_player_population,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)


def test_world_arrival_adds_to_abstract_population_and_logs_event(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Later Arrival",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    set_abstract_simulated_player_population(
        db_session,
        campaign.id,
        location.id,
        2,
    )

    population = (
        register_simulated_player_world_arrival(
            db_session,
            campaign.id,
            location.id,
            3,
        )
    )

    assert population.abstract_count == 5

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 5
    )

    event = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_WORLD_ARRIVAL.value,
        )
        .one()
    )

    payload = json.loads(
        event.payload_json
    )

    assert payload["location_id"] == location.id
    assert payload["count"] == 3