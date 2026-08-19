import json
import random
import pytest

from app.core.enums import EventType
from app.db.models.event import WorldEvent
from app.db.models.location import Location
from app.game.time.clock import get_world_time
from app.game.players.service import (
    set_simulated_player_arrival_location_enabled,
    simulated_player_arrival_locations,
    select_simulated_player_arrival_location,
    ensure_automatic_simulated_player_world_arrival_scheduled,
    ensure_simulated_player_world_arrival_scheduled,
    get_pending_simulated_player_world_arrival,
    schedule_simulated_player_world_arrival_from_policy,
    get_simulated_player_arrival_policy,
    set_simulated_player_arrival_policy,
    schedule_next_simulated_player_world_arrival,
    abstract_simulated_player_count_at_location,
    register_simulated_player_world_arrival,
    set_abstract_simulated_player_population,
    schedule_simulated_player_world_arrival,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)
from app.db.models.simulated_player_arrival import (
    ScheduledSimulatedPlayerArrival,
)
from app.game.time.clock import advance_world_time
from app.simulation import world_simulation

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

    assert (
        event.world_minute
        == campaign.world_time.total_minutes()
    )
    assert event.world_minute == get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    assert payload["location_id"] == location.id
    assert payload["count"] == 3

def test_future_arrival_is_persisted_without_happening_immediately(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Scheduled Arrival",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    current_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    scheduled_world_minute = (
        current_world_minute + 180
    )

    arrival = schedule_simulated_player_world_arrival(
        db_session,
        campaign.id,
        location.id,
        count=4,
        scheduled_world_minute=scheduled_world_minute,
    )

    assert arrival.location_id == location.id
    assert arrival.count == 4
    assert (
        arrival.scheduled_world_minute
        == scheduled_world_minute
    )
    assert arrival.executed_world_minute is None

    persisted = db_session.get(
        ScheduledSimulatedPlayerArrival,
        arrival.id,
    )

    assert persisted is not None
    assert persisted.id == arrival.id

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 0
    )

    arrival_events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_WORLD_ARRIVAL.value,
        )
        .all()
    )

    assert arrival_events == []

def test_scheduled_arrival_executes_once_at_canonical_world_minute(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Executed Scheduled Arrival",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    start_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    scheduled_world_minute = (
        start_world_minute + 120
    )

    arrival = schedule_simulated_player_world_arrival(
        db_session,
        campaign.id,
        location.id,
        count=3,
        scheduled_world_minute=(
            scheduled_world_minute
        ),
    )

    advance_world_time(
        db_session,
        campaign.id,
        240,
    )

    result = world_simulation.tick(
        db_session,
        campaign.id,
        240,
    )

    assert result.simulated_player_arrivals == 1

    db_session.refresh(arrival)

    assert (
        arrival.executed_world_minute
        == scheduled_world_minute
    )

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 3
    )

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_WORLD_ARRIVAL.value,
        )
        .all()
    )

    assert len(events) == 1
    assert (
        events[0].world_minute
        == scheduled_world_minute
    )

    advance_world_time(
        db_session,
        campaign.id,
        60,
    )

    second_result = world_simulation.tick(
        db_session,
        campaign.id,
        60,
    )

    assert (
        second_result.simulated_player_arrivals
        == 0
    )

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 3
    )

    events_after_second_tick = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id
            == campaign.id,
            WorldEvent.event_type
            == EventType.SIMULATED_PLAYER_WORLD_ARRIVAL.value,
        )
        .all()
    )

    assert len(events_after_second_tick) == 1

def test_next_arrival_is_scheduled_irregularly_inside_given_window(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Irregular Arrival",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    current_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    arrival = schedule_next_simulated_player_world_arrival(
        db_session,
        campaign.id,
        location.id,
        count=2,
        min_delay_minutes=100,
        max_delay_minutes=500,
        rng=random.Random(42),
    )

    delay = (
        arrival.scheduled_world_minute
        - current_world_minute
    )

    assert 100 <= delay <= 500
    assert arrival.count == 2
    assert arrival.executed_world_minute is None

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 0
    )

def test_arrival_policy_is_optional_and_persists_exact_campaign_values(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Arrival Policy",
    )

    assert (
        get_simulated_player_arrival_policy(
            db_session,
            campaign.id,
        )
        is None
    )

    policy = set_simulated_player_arrival_policy(
        db_session,
        campaign.id,
        enabled=True,
        min_delay_minutes=111,
        max_delay_minutes=777,
        min_group_size=2,
        max_group_size=9,
    )

    assert policy.campaign_id == campaign.id
    assert policy.enabled is True
    assert policy.min_delay_minutes == 111
    assert policy.max_delay_minutes == 777
    assert policy.min_group_size == 2
    assert policy.max_group_size == 9

    persisted = (
        get_simulated_player_arrival_policy(
            db_session,
            campaign.id,
        )
    )

    assert persisted is not None
    assert persisted.id == policy.id
    assert persisted.min_delay_minutes == 111
    assert persisted.max_delay_minutes == 777
    assert persisted.min_group_size == 2
    assert persisted.max_group_size == 9

def test_arrival_policy_schedules_future_arrival_within_configured_bounds(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Policy Scheduled Arrival",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    set_simulated_player_arrival_policy(
        db_session,
        campaign.id,
        enabled=True,
        min_delay_minutes=120,
        max_delay_minutes=600,
        min_group_size=2,
        max_group_size=5,
    )

    current_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    arrival = (
        schedule_simulated_player_world_arrival_from_policy(
            db_session,
            campaign.id,
            location.id,
            rng=random.Random(42),
        )
    )

    assert arrival is not None

    delay = (
        arrival.scheduled_world_minute
        - current_world_minute
    )

    assert 120 <= delay <= 600
    assert 2 <= arrival.count <= 5
    assert arrival.location_id == location.id
    assert arrival.executed_world_minute is None

    assert (
        abstract_simulated_player_count_at_location(
            db_session,
            campaign.id,
            location.id,
        )
        == 0
    )

def test_missing_arrival_policy_schedules_nothing(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "No Arrival Policy",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    arrival = (
        schedule_simulated_player_world_arrival_from_policy(
            db_session,
            campaign.id,
            location.id,
            rng=random.Random(42),
        )
    )

    assert arrival is None

def test_ensure_arrival_reuses_existing_pending_schedule(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Single Pending Arrival",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    set_simulated_player_arrival_policy(
        db_session,
        campaign.id,
        enabled=True,
        min_delay_minutes=100,
        max_delay_minutes=500,
        min_group_size=2,
        max_group_size=4,
    )

    first = ensure_simulated_player_world_arrival_scheduled(
        db_session,
        campaign.id,
        location.id,
        rng=random.Random(10),
    )

    second = ensure_simulated_player_world_arrival_scheduled(
        db_session,
        campaign.id,
        location.id,
        rng=random.Random(999),
    )

    assert first is not None
    assert second is not None
    assert second.id == first.id

    pending = get_pending_simulated_player_world_arrival(
        db_session,
        campaign.id,
    )

    assert pending is not None
    assert pending.id == first.id

    pending_rows = (
        db_session.query(
            ScheduledSimulatedPlayerArrival
        )
        .filter(
            ScheduledSimulatedPlayerArrival.executed_world_minute
            .is_(None),
        )
        .all()
    )

    assert len(pending_rows) == 1

def test_only_explicitly_enabled_locations_are_valid_for_automatic_arrivals(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Arrival Locations",
    )

    region, first_location = seed_initial_region(
        db_session,
        campaign.id,
    )

    other_location = Location(
        region_id=region.id,
        name="Other Place",
        type="forest",
    )

    db_session.add(other_location)
    db_session.flush()

    assert (
        simulated_player_arrival_locations(
            db_session,
            campaign.id,
        )
        == []
    )

    set_simulated_player_arrival_location_enabled(
        db_session,
        campaign.id,
        first_location.id,
        enabled=True,
    )

    enabled = simulated_player_arrival_locations(
        db_session,
        campaign.id,
    )

    assert [location.id for location in enabled] == [
        first_location.id
    ]

    set_simulated_player_arrival_location_enabled(
        db_session,
        campaign.id,
        first_location.id,
        enabled=False,
    )

    assert (
        simulated_player_arrival_locations(
            db_session,
            campaign.id,
        )
        == []
    )

def test_arrival_location_selector_uses_only_explicitly_enabled_locations(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Arrival Location Selection",
    )

    region, first_location = seed_initial_region(
        db_session,
        campaign.id,
    )

    second_location = Location(
        region_id=region.id,
        name="Second Arrival Place",
        type="forest",
    )

    third_location = Location(
        region_id=region.id,
        name="Not An Arrival Place",
        type="village",
    )

    db_session.add_all(
        [
            second_location,
            third_location,
        ]
    )
    db_session.flush()

    assert (
        select_simulated_player_arrival_location(
            db_session,
            campaign.id,
            rng=random.Random(42),
        )
        is None
    )

    set_simulated_player_arrival_location_enabled(
        db_session,
        campaign.id,
        first_location.id,
        enabled=True,
    )

    set_simulated_player_arrival_location_enabled(
        db_session,
        campaign.id,
        second_location.id,
        enabled=True,
    )

    selected = select_simulated_player_arrival_location(
        db_session,
        campaign.id,
        rng=random.Random(42),
    )

    assert selected is not None
    assert selected.id in {
        first_location.id,
        second_location.id,
    }

    assert selected.id != third_location.id

def test_automatic_arrival_scheduler_combines_policy_location_and_pending_guard(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Automatic Arrival Scheduling",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    set_simulated_player_arrival_policy(
        db_session,
        campaign.id,
        enabled=True,
        min_delay_minutes=100,
        max_delay_minutes=500,
        min_group_size=2,
        max_group_size=4,
    )

    # Policy alone is not enough.
    # No location has explicitly been enabled yet.
    missing_location = (
        ensure_automatic_simulated_player_world_arrival_scheduled(
            db_session,
            campaign.id,
            rng=random.Random(42),
        )
    )

    assert missing_location is None

    set_simulated_player_arrival_location_enabled(
        db_session,
        campaign.id,
        location.id,
        enabled=True,
    )

    first = (
        ensure_automatic_simulated_player_world_arrival_scheduled(
            db_session,
            campaign.id,
            rng=random.Random(42),
        )
    )

    assert first is not None
    assert first.location_id == location.id
    assert first.executed_world_minute is None
    assert 2 <= first.count <= 4

    second = (
        ensure_automatic_simulated_player_world_arrival_scheduled(
            db_session,
            campaign.id,
            rng=random.Random(999),
        )
    )

    assert second is not None
    assert second.id == first.id