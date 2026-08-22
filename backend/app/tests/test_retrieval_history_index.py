"""Phase 18C — Historical Event Index."""

from app.ai.retrieval.documents import documents_for_source
from app.ai.retrieval.history import HISTORICAL_EVENT_MIN_IMPORTANCE, index_historical_event
from app.core.enums import EventType, KnowledgeDocumentType, KnowledgeSourceType
from app.db.models.knowledge_index import IndexedKnowledgeDocument
from app.game.world.seed import create_campaign
from app.services.event_log import log_event


def test_important_events_are_indexed_automatically_by_log_event(db_session):
    campaign = create_campaign(db_session, "Historia Importante")

    event = log_event(
        db_session,
        campaign.id,
        EventType.PLAYER_LEVELED_UP,
        actor_type="character",
        actor_id="char_1",
        payload={"new_level": 2},
    )

    assert event.importance == 4
    docs = documents_for_source(db_session, campaign.id, KnowledgeSourceType.EVENT, event.id)
    assert len(docs) == 1
    assert docs[0].document_type == KnowledgeDocumentType.HISTORICAL_EVENT.value
    assert "Level 2" in docs[0].text
    assert docs[0].occurred_world_minute == event.world_minute


def test_routine_low_importance_events_are_not_indexed(db_session):
    campaign = create_campaign(db_session, "Rotina Nao Historica")

    event = log_event(db_session, campaign.id, EventType.PLAYER_RESTED)

    assert event.importance < HISTORICAL_EVENT_MIN_IMPORTANCE
    assert documents_for_source(db_session, campaign.id, KnowledgeSourceType.EVENT, event.id) == []


def test_index_historical_event_returns_none_below_threshold(db_session):
    campaign = create_campaign(db_session, "Abaixo Do Limiar")
    event = log_event(db_session, campaign.id, EventType.PLAYER_RESTED)

    assert index_historical_event(db_session, event) is None


def test_historical_event_index_is_campaign_scoped(db_session):
    first = create_campaign(db_session, "Campanha Historica A")
    second = create_campaign(db_session, "Campanha Historica B")

    event = log_event(
        db_session, first.id, EventType.PLAYER_LEVELED_UP,
        actor_type="character", actor_id="char_x", payload={"new_level": 3},
    )

    assert documents_for_source(db_session, first.id, KnowledgeSourceType.EVENT, event.id) != []
    assert documents_for_source(db_session, second.id, KnowledgeSourceType.EVENT, event.id) == []
    assert (
        db_session.query(IndexedKnowledgeDocument)
        .filter(IndexedKnowledgeDocument.campaign_id == second.id)
        .count()
        == 0
    )
