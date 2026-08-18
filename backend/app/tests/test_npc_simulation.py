from app.core.enums import NPCActivity
from app.db.models.npc import NPC
from app.game.time.clock import advance_world_time
from app.game.world.seed import create_campaign, seed_initial_region
from app.simulation import npc_simulation


def _setup_world(db_session):
    campaign = create_campaign(
        db_session,
        "NPC Simulation",
    )

    seed_initial_region(
        db_session,
        campaign.id,
    )

    db_session.flush()

    return campaign


def test_npc_tick_updates_daily_activity(
    db_session,
):
    campaign = _setup_world(db_session)

    blacksmith = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
            NPC.role == "ferreira",
        )
        .one()
    )

    assert blacksmith.activity == NPCActivity.AVAILABLE

    # 08:00 -> 08:10
    advance_world_time(
        db_session,
        campaign.id,
        10,
    )

    result = npc_simulation.tick(
        db_session,
        campaign.id,
        10,
    )

    assert blacksmith.activity == NPCActivity.WORKING
    assert result.changes >= 1


def test_npc_tick_does_not_count_unchanged_activity(
    db_session,
):
    campaign = _setup_world(db_session)

    advance_world_time(
        db_session,
        campaign.id,
        10,
    )

    first_result = npc_simulation.tick(
        db_session,
        campaign.id,
        10,
    )

    assert first_result.changes > 0

    # 08:10 -> 08:20.
    # A rotina continua igual.
    advance_world_time(
        db_session,
        campaign.id,
        10,
    )

    second_result = npc_simulation.tick(
        db_session,
        campaign.id,
        10,
    )

    assert second_result.changes == 0


def test_npc_tick_changes_worker_to_resting_at_night(
    db_session,
):
    campaign = _setup_world(db_session)

    # Primeiro sincroniza a rotina das 08:00.
    npc_simulation.tick(
        db_session,
        campaign.id,
        1,
    )

    blacksmith = (
        db_session.query(NPC)
        .filter(
            NPC.campaign_id == campaign.id,
            NPC.role == "ferreira",
        )
        .one()
    )

    assert blacksmith.activity == NPCActivity.WORKING

    # 08:00 -> 22:00
    advance_world_time(
        db_session,
        campaign.id,
        14 * 60,
    )

    result = npc_simulation.tick(
        db_session,
        campaign.id,
        14 * 60,
    )

    assert blacksmith.activity == NPCActivity.RESTING
    assert result.changes >= 1


def test_npc_tick_with_zero_minutes_changes_nothing(
    db_session,
):
    campaign = _setup_world(db_session)

    result = npc_simulation.tick(
        db_session,
        campaign.id,
        0,
    )

    assert result.changes == 0