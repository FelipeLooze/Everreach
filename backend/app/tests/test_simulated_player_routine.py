import pytest

from app.core.enums import (
    SimulatedPlayerActivity,
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
)
from app.db.models.location import Location
from app.game.time.clock import (
    advance_world_time,
    get_world_time,
)
from app.db.models.simulated_player_routine import (
    SimulatedPlayerRoutine,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)
from app.game.players.service import (
    create_simulated_player_routine,
    disable_simulated_player_routine,
    simulated_players_at_location,
)
from app.simulation import player_simulation

def test_established_routine_can_be_persisted(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Established Routine",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    current_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    routine = SimulatedPlayerRoutine(
        simulated_player_id=player.id,
        location_id=location.id,
        activity=SimulatedPlayerActivity.TRAINING.value,
        start_minute_of_day=8 * 60,
        end_minute_of_day=10 * 60,
        established_world_minute=current_world_minute,
        enabled=True,
    )

    db_session.add(routine)
    db_session.flush()

    persisted = db_session.get(
        SimulatedPlayerRoutine,
        routine.id,
    )

    assert persisted is not None
    assert persisted.simulated_player_id == player.id
    assert persisted.location_id == location.id

    assert (
        persisted.activity
        == SimulatedPlayerActivity.TRAINING.value
    )

    assert persisted.start_minute_of_day == 480
    assert persisted.end_minute_of_day == 600

    assert (
        persisted.established_world_minute
        == current_world_minute
    )

    assert persisted.enabled is True

def test_transportee_can_have_multiple_established_routines(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Multiple Established Routines",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    current_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    routines = [
        SimulatedPlayerRoutine(
            simulated_player_id=player.id,
            location_id=location.id,
            activity=SimulatedPlayerActivity.TRAINING.value,
            start_minute_of_day=8 * 60,
            end_minute_of_day=10 * 60,
            established_world_minute=current_world_minute,
        ),
        SimulatedPlayerRoutine(
            simulated_player_id=player.id,
            location_id=location.id,
            activity=SimulatedPlayerActivity.SOCIALIZING.value,
            start_minute_of_day=18 * 60,
            end_minute_of_day=19 * 60,
            established_world_minute=current_world_minute,
        ),
    ]

    db_session.add_all(routines)
    db_session.flush()

    persisted = (
        db_session.query(SimulatedPlayerRoutine)
        .filter(
            SimulatedPlayerRoutine.simulated_player_id
            == player.id,
        )
        .order_by(
            SimulatedPlayerRoutine.start_minute_of_day
        )
        .all()
    )

    assert len(persisted) == 2

    assert persisted[0].activity == (
        SimulatedPlayerActivity.TRAINING.value
    )

    assert persisted[1].activity == (
        SimulatedPlayerActivity.SOCIALIZING.value
    )

def test_service_creates_established_routine(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Established Routine Service",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    current_world_minute = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    routine = create_simulated_player_routine(
        db_session,
        player,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    assert routine.simulated_player_id == player.id
    assert routine.location_id == location.id

    assert (
        routine.activity
        == SimulatedPlayerActivity.TRAINING.value
    )

    assert routine.start_minute_of_day == 480
    assert routine.end_minute_of_day == 600

    assert (
        routine.established_world_minute
        == current_world_minute
    )

    assert routine.enabled is True

def test_established_routines_cannot_overlap(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Overlapping Routines",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    create_simulated_player_routine(
        db_session,
        player,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    with pytest.raises(ValueError):
        create_simulated_player_routine(
            db_session,
            player,
            location.id,
            SimulatedPlayerActivity.SOCIALIZING,
            9 * 60,
            11 * 60,
        )

def test_established_routines_can_touch_without_overlap(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Adjacent Routines",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    first = create_simulated_player_routine(
        db_session,
        player,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    second = create_simulated_player_routine(
        db_session,
        player,
        location.id,
        SimulatedPlayerActivity.SOCIALIZING,
        10 * 60,
        11 * 60,
    )

    assert first.enabled is True
    assert second.enabled is True

@pytest.mark.parametrize(
    "activity",
    [
        SimulatedPlayerActivity.AVAILABLE,
        SimulatedPlayerActivity.RESTING,
    ],
)
def test_rejects_invalid_established_routine_activity(
    db_session,
    activity,
):
    campaign = create_campaign(
        db_session,
        "Invalid Established Routine",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    with pytest.raises(ValueError):
        create_simulated_player_routine(
            db_session,
            player,
            location.id,
            activity,
            8 * 60,
            10 * 60,
        )

def test_established_routine_must_end_after_start(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Invalid Routine Time",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    with pytest.raises(ValueError):
        create_simulated_player_routine(
            db_session,
            player,
            location.id,
            SimulatedPlayerActivity.TRAINING,
            10 * 60,
            8 * 60,
        )

def test_established_routine_can_be_disabled(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Disable Established Routine",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    routine = create_simulated_player_routine(
        db_session,
        player,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    result = disable_simulated_player_routine(
        db_session,
        routine,
    )

    assert result is routine
    assert routine.enabled is False

def test_established_training_runs_only_inside_daily_window(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Established Training Execution",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    social = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.SOCIAL
    )

    social.goal_type = (
        SimulatedPlayerGoalType.NONE
    )

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    world_time.hour = 7
    world_time.minute = 0

    create_simulated_player_routine(
        db_session,
        social,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    db_session.flush()

    # Isolate the established routine from normal archetype actions.
    monkeypatch.setattr(
        player_simulation,
        "ACTION_CHANCE_PER_HOUR",
        0.0,
    )

    # 07:00 -> 11:00
    #
    # Hourly opportunities:
    # 08:00 -> training
    # 09:00 -> training
    # 10:00 -> routine already ended
    # 11:00 -> outside routine
    advance_world_time(
        db_session,
        campaign.id,
        4 * 60,
    )

    result = player_simulation.tick(
        db_session,
        campaign.id,
        4 * 60,
    )

    assert result.trained == 2

    assert (
        social.activity
        == SimulatedPlayerActivity.AVAILABLE.value
    )

    assert social.activity_until_world_minute is None

def test_established_routine_only_runs_at_configured_location(
    db_session,
    monkeypatch,
):
    campaign = create_campaign(
        db_session,
        "Routine Location",
    )

    region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    players = simulated_players_at_location(
        db_session,
        location.id,
    )

    social = next(
        player
        for player in players
        if player.archetype
        == SimulatedPlayerArchetype.SOCIAL
    )

    social.goal_type = (
        SimulatedPlayerGoalType.NONE
    )

    other_location = (
        db_session.query(Location)
        .filter(
            Location.region_id == region.id,
            Location.id != location.id,
        )
        .first()
    )

    assert other_location is not None

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    world_time.hour = 7
    world_time.minute = 0

    create_simulated_player_routine(
        db_session,
        social,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    # The person is physically elsewhere.
    social.location_id = other_location.id

    db_session.flush()

    # Isolate this location rule from unrelated archetype actions
    # performed by the other seeded transported people.
    monkeypatch.setattr(
        player_simulation,
        "ACTION_CHANCE_PER_HOUR",
        0.0,
    )

    advance_world_time(
        db_session,
        campaign.id,
        2 * 60,
    )

    result = player_simulation.tick(
        db_session,
        campaign.id,
        2 * 60,
    )

    assert result.trained == 0

    assert social.location_id == other_location.id

def test_established_routine_is_not_applied_retroactively(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Routine Historical Boundary",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    world_time.hour = 9
    world_time.minute = 30

    current_world_minute = (
        world_time.total_minutes()
    )

    create_simulated_player_routine(
        db_session,
        player,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    player.activity = (
        SimulatedPlayerActivity.AVAILABLE.value
    )
    player.activity_until_world_minute = None

    db_session.flush()

    # Ask the simulation about 09:00, even though the routine
    # was only established at 09:30.
    player_simulation._sync_established_routine(
        db_session,
        player,
        current_world_minute - 30,
    )

    assert (
        player.activity
        == SimulatedPlayerActivity.AVAILABLE.value
    )

    assert player.activity_until_world_minute is None

def test_temporary_activity_has_priority_over_established_routine(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Temporary Activity Priority",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    world_time.hour = 8
    world_time.minute = 0

    current_world_minute = (
        world_time.total_minutes()
    )

    create_simulated_player_routine(
        db_session,
        player,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    player.activity = (
        SimulatedPlayerActivity.SOCIALIZING.value
    )

    player.activity_until_world_minute = (
        current_world_minute + 30
    )

    db_session.flush()

    player_simulation._sync_established_routine(
        db_session,
        player,
        current_world_minute + 10,
    )

    assert (
        player.activity
        == SimulatedPlayerActivity.SOCIALIZING.value
    )

    assert (
        player.activity_until_world_minute
        == current_world_minute + 30
    )

def test_short_tick_enters_established_routine_without_hour_boundary(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Short Established Routine Tick",
    )

    _region, location = seed_initial_region(
        db_session,
        campaign.id,
    )

    player = simulated_players_at_location(
        db_session,
        location.id,
    )[0]

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    world_time.hour = 8
    world_time.minute = 0

    start_world_minute = (
        world_time.total_minutes()
    )

    create_simulated_player_routine(
        db_session,
        player,
        location.id,
        SimulatedPlayerActivity.TRAINING,
        8 * 60,
        10 * 60,
    )

    db_session.flush()

    # 08:00 -> 08:10.
    # No hourly mechanical opportunity occurs.
    advance_world_time(
        db_session,
        campaign.id,
        10,
    )

    result = player_simulation.tick(
        db_session,
        campaign.id,
        10,
    )

    assert result.trained == 0

    assert (
        player.activity
        == SimulatedPlayerActivity.TRAINING.value
    )

    assert (
        player.activity_until_world_minute
        == start_world_minute + (2 * 60)
    )