import json

import pytest
from app.db.models.event import WorldEvent
from app.game.time.clock import get_world_time
from app.db.models.memory import Memory
from app.game.time.clock import advance_world_time
from app.simulation import development_simulation
from app.core.enums import (
    EventType,
    WorldDevelopmentStatus,
    WorldDevelopmentType,
)
from app.game.developments.service import (
    create_world_development,
)
from app.game.world.seed import (
    create_campaign,
    seed_initial_region,
)
from app.db.models.knowledge import (
    KnowledgeFact,
    KnowledgeKnower,
)


def test_create_world_development_sets_schedule(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Development Service",
    )

    region, village = seed_initial_region(
        db_session,
        campaign.id,
    )

    now = get_world_time(
        db_session,
        campaign.id,
    ).total_minutes()

    interval = 7 * 24 * 60

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Nova ponte",
        interval_minutes=interval,
        payload={
            "progress": 0,
            "progress_per_update": 10,
        },
        location_id=village.id,
        description="Uma ponte está sendo construída.",
    )

    payload = json.loads(
        development.payload_json
    )

    assert development.campaign_id == campaign.id
    assert development.region_id == region.id
    assert development.location_id == village.id

    assert (
        development.development_type
        == WorldDevelopmentType.CONSTRUCTION.value
    )

    assert (
        development.status
        == WorldDevelopmentStatus.ACTIVE.value
    )

    assert development.started_world_minute == now
    assert development.last_updated_world_minute is None

    assert (
        development.next_update_world_minute
        == now + interval
    )

    assert payload == {
        "progress": 0,
        "progress_per_update": 10,
        "interval_minutes": interval,
    }

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == development.id,
            WorldEvent.event_type
            == EventType.WORLD_DEVELOPMENT_CREATED.value,
        )
        .all()
    )

    assert len(events) == 1

    event = events[0]

    assert event.world_minute == now
    assert event.importance == 1

    event_payload = json.loads(
        event.payload_json
    )

    assert event_payload == {
        "development_id": development.id,
        "development_type": (
            WorldDevelopmentType.CONSTRUCTION.value
        ),
        "title": "Nova ponte",
        "region_id": region.id,
        "location_id": village.id,
        "status": WorldDevelopmentStatus.ACTIVE.value,
    }


def test_create_world_development_rejects_invalid_interval(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Invalid Development",
    )

    with pytest.raises(
        ValueError,
        match="interval_minutes",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção inválida",
            interval_minutes=0,
        )


def test_create_world_development_rejects_location_from_other_campaign(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Campaign A",
    )

    other_campaign = create_campaign(
        db_session,
        "Campaign B",
    )

    _other_region, other_location = (
        seed_initial_region(
            db_session,
            other_campaign.id,
        )
    )

    with pytest.raises(
        ValueError,
        match="location does not belong to campaign",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção impossível",
            interval_minutes=7 * 24 * 60,
            location_id=other_location.id,
        )

def test_create_construction_defaults_progress_to_zero(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Construction Defaults",
    )

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Nova construção",
        interval_minutes=7 * 24 * 60,
        payload={
            "progress_per_update": 10,
        },
    )

    payload = json.loads(
        development.payload_json
    )

    assert payload["progress"] == 0
    assert payload["progress_per_update"] == 10


def test_create_construction_rejects_invalid_progress(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Invalid Construction Progress",
    )

    with pytest.raises(
        ValueError,
        match="progress must be between 0 and 100",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção inválida",
            interval_minutes=7 * 24 * 60,
            payload={
                "progress": 120,
                "progress_per_update": 10,
            },
        )


def test_create_construction_requires_positive_progress_per_update(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Invalid Construction Rate",
    )

    with pytest.raises(
        ValueError,
        match="progress_per_update",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção sem ritmo",
            interval_minutes=7 * 24 * 60,
            payload={
                "progress": 0,
            },
        )

def test_create_construction_rejects_already_completed_progress(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Completed Construction",
    )

    with pytest.raises(
        ValueError,
        match="active construction progress must be below 100",
    ):
        create_world_development(
            db_session,
            campaign.id,
            WorldDevelopmentType.CONSTRUCTION,
            "Construção já pronta",
            interval_minutes=7 * 24 * 60,
            payload={
                "progress": 100,
                "progress_per_update": 10,
            },
        )

def test_world_development_events_do_not_create_automatic_memory_or_knowledge(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Hidden World Development",
    )

    interval = 7 * 24 * 60

    memory_count_before = (
        db_session.query(Memory).count()
    )

    fact_count_before = (
        db_session.query(KnowledgeFact).count()
    )

    knower_count_before = (
        db_session.query(KnowledgeKnower).count()
    )

    development = create_world_development(
        db_session,
        campaign.id,
        WorldDevelopmentType.CONSTRUCTION,
        "Ponte distante",
        interval_minutes=interval,
        payload={
            "progress": 90,
            "progress_per_update": 10,
        },
    )

    # A criação já gerou WORLD_DEVELOPMENT_CREATED,
    # mas isso continua sendo apenas World Truth.
    assert (
        db_session.query(Memory).count()
        == memory_count_before
    )

    assert (
        db_session.query(KnowledgeFact).count()
        == fact_count_before
    )

    assert (
        db_session.query(KnowledgeKnower).count()
        == knower_count_before
    )

    # Faz a construção chegar ao próximo vencimento
    # e concluir fora da percepção de qualquer personagem.
    advance_world_time(
        db_session,
        campaign.id,
        interval,
    )

    result = development_simulation.tick(
        db_session,
        campaign.id,
        interval,
    )

    db_session.flush()

    assert result.changes == 1

    events = (
        db_session.query(WorldEvent)
        .filter(
            WorldEvent.actor_id == development.id,
        )
        .order_by(WorldEvent.world_minute.asc())
        .all()
    )

    assert [
        event.event_type
        for event in events
    ] == [
        EventType.WORLD_DEVELOPMENT_CREATED.value,
        EventType.WORLD_DEVELOPMENT_COMPLETED.value,
    ]

    assert (
        db_session.query(Memory).count()
        == memory_count_before
    )

    assert (
        db_session.query(KnowledgeFact).count()
        == fact_count_before
    )

    assert (
        db_session.query(KnowledgeKnower).count()
        == knower_count_before
    )