import pytest
from app.core.enums import SimulatedPlayerActivity
from app.game.time.clock import get_world_time
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