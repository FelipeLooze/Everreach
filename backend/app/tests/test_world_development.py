from app.core.enums import WorldDevelopmentStatus
from app.db.models.world_development import WorldDevelopment
from app.game.world.reset import delete_campaign
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)


def test_world_development_persists_with_defaults(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "World Development",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    development = WorldDevelopment(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=village.id,
        development_type="TEST",
        title="Construção de teste",
    )

    db_session.add(development)
    db_session.flush()

    assert development.id.startswith("dev_")
    assert (
        development.status
        == WorldDevelopmentStatus.PLANNED.value
    )
    assert development.description == ""
    assert development.payload_json == "{}"

    assert development.started_world_minute is None
    assert development.last_updated_world_minute is None
    assert development.next_update_world_minute is None


def test_world_development_can_store_world_schedule(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Scheduled Development",
    )

    development = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        status=WorldDevelopmentStatus.ACTIVE.value,
        title="Expedição de teste",
        started_world_minute=1000,
        last_updated_world_minute=1000,
        next_update_world_minute=1000 + 7 * 24 * 60,
        payload_json='{"progress": 10}',
    )

    db_session.add(development)
    db_session.flush()

    stored = db_session.get(
        WorldDevelopment,
        development.id,
    )

    assert stored is not None
    assert (
        stored.status
        == WorldDevelopmentStatus.ACTIVE.value
    )
    assert stored.started_world_minute == 1000
    assert stored.last_updated_world_minute == 1000
    assert (
        stored.next_update_world_minute
        == 1000 + 7 * 24 * 60
    )
    assert stored.payload_json == '{"progress": 10}'


def test_delete_campaign_removes_world_developments(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Reset",
    )

    development = WorldDevelopment(
        campaign_id=campaign.id,
        development_type="TEST",
        title="Desenvolvimento temporário",
    )

    db_session.add(development)
    db_session.flush()

    development_id = development.id

    assert (
        db_session.get(
            WorldDevelopment,
            development_id,
        )
        is not None
    )

    deleted = delete_campaign(
        db_session,
        campaign.id,
    )

    assert deleted is True
    assert (
        db_session.query(WorldDevelopment)
        .filter(WorldDevelopment.id == development_id)
        .count() == 0
    )