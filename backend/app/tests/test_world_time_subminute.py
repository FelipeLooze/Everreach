from app.game.time.clock import (
    advance_world_time_seconds,
    get_world_time,
)
from app.game.world.seed import create_campaign

def test_subminute_seconds_accumulate_until_whole_minute(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Subminute Time",
    )

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    assert world_time.hour == 8
    assert world_time.minute == 0
    assert world_time.subminute_seconds == 0

    crossed_minutes = advance_world_time_seconds(
        db_session,
        campaign.id,
        20,
    )

    assert crossed_minutes == 0
    assert world_time.hour == 8
    assert world_time.minute == 0
    assert world_time.subminute_seconds == 20

    crossed_minutes = advance_world_time_seconds(
        db_session,
        campaign.id,
        50,
    )

    assert crossed_minutes == 1
    assert world_time.hour == 8
    assert world_time.minute == 1
    assert world_time.subminute_seconds == 10

def test_subminute_seconds_are_persistent(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Persistent Subminute Time",
    )

    advance_world_time_seconds(
        db_session,
        campaign.id,
        47,
    )

    db_session.flush()
    db_session.expire_all()

    world_time = get_world_time(
        db_session,
        campaign.id,
    )

    assert world_time.minute == 0
    assert world_time.subminute_seconds == 47

    