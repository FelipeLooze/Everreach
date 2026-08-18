from app.core.enums import EventType
from app.db.models.knowledge import (
    KnowledgeFact,
    KnowledgeKnower,
)
from app.game.knowledge.service import (
    create_event_fact,
)
from app.game.world.seed import create_campaign
from app.services.event_log import log_event


def test_create_event_fact_records_world_truth_without_knower(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Event Fact",
    )

    event = log_event(
        db_session,
        campaign.id,
        EventType.WORLD_DEVELOPMENT_CREATED,
        actor_type="world_development",
        actor_id="dev_test",
        payload={},
    )

    fact = create_event_fact(
        db_session,
        event,
        subject="world_development:dev_test",
        statement=(
            "Uma ponte começou a ser construída."
        ),
    )

    assert fact.campaign_id == campaign.id
    assert fact.subject == (
        "world_development:dev_test"
    )

    assert fact.fact_key == (
        f"world_event:{event.id}"
    )

    assert fact.statement == (
        "Uma ponte começou a ser construída."
    )

    assert fact.is_secret is False

    assert (
        db_session.query(KnowledgeKnower)
        .filter(
            KnowledgeKnower.fact_id == fact.id
        )
        .count()
        == 0
    )


def test_create_event_fact_is_idempotent(
    db_session,
):
    campaign = create_campaign(
        db_session,
        "Idempotent Event Fact",
    )

    event = log_event(
        db_session,
        campaign.id,
        EventType.WORLD_DEVELOPMENT_UPDATED,
        actor_type="world_development",
        actor_id="dev_test",
        payload={},
    )

    first = create_event_fact(
        db_session,
        event,
        subject="world_development:dev_test",
        statement="A construção atingiu 10%.",
    )

    second = create_event_fact(
        db_session,
        event,
        subject="world_development:dev_test",
        statement="A construção atingiu 10%.",
    )

    assert second.id == first.id

    assert (
        db_session.query(KnowledgeFact)
        .filter(
            KnowledgeFact.fact_key
            == f"world_event:{event.id}"
        )
        .count()
        == 1
    )