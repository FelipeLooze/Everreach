import pytest

from app.core.enums import (
    SimulatedPlayerActivity,
)
from app.game.players.service import (
    simulated_players_at_location,
    start_simulated_player_temporary_activity,
)
from app.game.time.clock import get_world_time
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)

def test_can_start_temporary_training(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Temporary Activity Service",
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

    until_world_minute = (
        current_world_minute + 120
    )

    result = start_simulated_player_temporary_activity(
        db_session,
        player,
        SimulatedPlayerActivity.TRAINING,
        until_world_minute,
    )

    assert result is player

    assert (
        player.activity
        == SimulatedPlayerActivity.TRAINING.value
    )

    assert (
        player.activity_until_world_minute
        == until_world_minute
    )


@pytest.mark.parametrize(
    "activity",
    [
        SimulatedPlayerActivity.AVAILABLE,
        SimulatedPlayerActivity.RESTING,
    ],
)
def test_rejects_non_temporary_activity_types(
    db_session,
    activity,
):
    campaign = create_campaign(
        db_session,
        "Invalid Temporary Activity",
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

    with pytest.raises(ValueError):
        start_simulated_player_temporary_activity(
            db_session,
            player,
            activity,
            current_world_minute + 60,
        )


def test_temporary_activity_must_end_in_future(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Temporary Activity Time Validation",
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

    with pytest.raises(ValueError):
        start_simulated_player_temporary_activity(
            db_session,
            player,
            SimulatedPlayerActivity.TRAINING,
            current_world_minute,
        )


def test_cannot_start_temporary_activity_while_traveling(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Travel Blocks Temporary Activity",
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

    player.travel_arrival_world_minute = (
        current_world_minute + 120
    )

    db_session.flush()

    with pytest.raises(ValueError):
        start_simulated_player_temporary_activity(
            db_session,
            player,
            SimulatedPlayerActivity.TRAINING,
            current_world_minute + 60,
        )
