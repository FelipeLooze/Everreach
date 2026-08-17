from app.db.models.campaign import WorldTime
from app.game.time.clock import advance_world_time
from app.game.world.seed import create_campaign


def test_advance_world_time_rolls_over_minutes_to_hours(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    db_session.commit()

    world_time = advance_world_time(db_session, campaign.id, 90)
    assert world_time.hour == 9
    assert world_time.minute == 30


def test_advance_world_time_rolls_over_days(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    db_session.commit()

    advance_world_time(db_session, campaign.id, 24 * 60)
    world_time = db_session.query(WorldTime).filter(WorldTime.campaign_id == campaign.id).first()
    assert world_time.day == 2


def test_advance_world_time_is_noop_for_zero_minutes(db_session):
    campaign = create_campaign(db_session, "Test Campaign")
    db_session.commit()

    before = db_session.query(WorldTime).filter(WorldTime.campaign_id == campaign.id).first()
    before_minute = before.minute

    advance_world_time(db_session, campaign.id, 0)
    after = db_session.query(WorldTime).filter(WorldTime.campaign_id == campaign.id).first()
    assert after.minute == before_minute
