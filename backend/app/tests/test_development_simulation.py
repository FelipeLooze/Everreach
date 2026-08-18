from app.simulation import development_simulation
from app.core.enums import WorldDevelopmentStatus
from app.db.models.world_development import WorldDevelopment
from app.game.time.clock import get_world_time
from app.game.world.seed import create_campaign

def test_development_simulation_currently_makes_no_changes(
    db_session,
):
    result = development_simulation.tick(
        db_session,
        "campaign_test",
        60,
    )

    assert result.changes == 0


def test_development_simulation_ignores_non_positive_time(
    db_session,
):
    zero = development_simulation.tick(
        db_session,
        "campaign_test",
        0,
    )

    negative = development_simulation.tick(
        db_session,
        "campaign_test",
        -10,
    )

    assert zero.changes == 0
    assert negative.changes == 0

def test_due_developments_returns_active_development_due_now(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Due Development",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    development = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Desenvolvimento vencido",
        next_update_world_minute=now,
    )

    db_session.add(development)
    db_session.flush()

    due = development_simulation.due_developments(
        db_session,
        campaign.id,
    )

    assert [item.id for item in due] == [
        development.id
    ]


def test_due_developments_excludes_not_due_or_ineligible_entries(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Filters",
    )

    other_campaign = create_campaign(
        db_session,
        "Other Campaign",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    due = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Devido",
        next_update_world_minute=now,
    )

    future = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Futuro",
        next_update_world_minute=now + 60,
    )

    planned = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.PLANNED.value,
        title="Planejado",
        next_update_world_minute=now,
    )

    unscheduled = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Sem agendamento",
        next_update_world_minute=None,
    )

    other = WorldDevelopment(
        campaign_id=other_campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Outra campanha",
        next_update_world_minute=now,
    )

    db_session.add_all(
        [
            due,
            future,
            planned,
            unscheduled,
            other,
        ]
    )
    db_session.flush()

    result = development_simulation.due_developments(
        db_session,
        campaign.id,
    )

    assert [item.id for item in result] == [
        due.id
    ]


def test_due_developments_are_returned_in_deterministic_order(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Order",
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    later = WorldDevelopment(
        id="dev_c",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Mais tarde",
        next_update_world_minute=now,
    )

    second = WorldDevelopment(
        id="dev_b",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Segundo",
        next_update_world_minute=now - 60,
    )

    first = WorldDevelopment(
        id="dev_a",
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Primeiro",
        next_update_world_minute=now - 60,
    )

    db_session.add_all(
        [
            later,
            second,
            first,
        ]
    )
    db_session.flush()

    result = development_simulation.due_developments(
        db_session,
        campaign.id,
    )

    assert [item.id for item in result] == [
        "dev_a",
        "dev_b",
        "dev_c",
    ]