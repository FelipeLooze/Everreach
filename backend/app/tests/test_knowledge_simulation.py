from app.game.time.clock import (
    advance_world_time,
)
from app.game.world.seed import create_campaign
from app.simulation import knowledge_simulation


def test_knowledge_simulation_has_no_opportunity_without_daily_boundary(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Knowledge Cadence Short",
    )

    advance_world_time(
        db_session,
        campaign.id,
        60,
    )

    result = knowledge_simulation.tick(
        db_session,
        campaign.id,
        60,
    )

    assert result.opportunity_world_minutes == ()
    assert result.opportunities == 0
    assert result.propagations == 0
    assert result.resolvable_opportunities == 0


def test_knowledge_simulation_counts_daily_boundaries(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Knowledge Cadence Daily",
    )

    minutes = 24 * 60

    advance_world_time(
        db_session,
        campaign.id,
        minutes,
    )

    result = knowledge_simulation.tick(
        db_session,
        campaign.id,
        minutes,
    )

    assert result.opportunities == 1
    assert result.propagations == 0
    assert (
        result.opportunity_world_minutes
        == (24 * 60,)
    )
    assert result.opportunities == 1
    assert result.resolvable_opportunities == 1


def test_knowledge_simulation_catches_up_multiple_days(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Knowledge Cadence Catch Up",
    )

    minutes = 7 * 24 * 60

    advance_world_time(
        db_session,
        campaign.id,
        minutes,
    )

    result = knowledge_simulation.tick(
        db_session,
        campaign.id,
        minutes,
    )

    assert result.opportunities == 7
    assert result.propagations == 0
    assert (
        result.opportunity_world_minutes
        == (
            1 * 24 * 60,
            2 * 24 * 60,
            3 * 24 * 60,
            4 * 24 * 60,
            5 * 24 * 60,
            6 * 24 * 60,
            7 * 24 * 60,
        )
    )
    assert result.opportunities == 7
    assert (
        result.resolvable_opportunities
        == 1
    )