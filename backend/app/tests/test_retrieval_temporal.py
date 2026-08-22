"""Phase 18J — Temporal Retrieval."""

from app.ai.retrieval.documents import upsert_document
from app.ai.retrieval.temporal import (
    documents_at_time,
    documents_current,
    documents_during_period,
    documents_historical,
    documents_recent,
)
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.game.world.seed import create_campaign


def test_documents_current_excludes_historical(db_session):
    campaign = create_campaign(db_session, "Temporal Atual")
    document = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "npc_fake",
        KnowledgeDocumentType.CURRENT_STATE, "Mira é a ferreira.",
    )

    assert documents_current(db_session, campaign.id) == [document]
    document.is_current = False
    db_session.flush()
    assert documents_current(db_session, campaign.id) == []


def test_documents_historical_only_returns_superseded_documents(db_session):
    campaign = create_campaign(db_session, "Temporal Historico")
    current = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "npc_fake",
        KnowledgeDocumentType.CURRENT_STATE, "Ainda atual.",
    )
    superseded = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "npc_other",
        KnowledgeDocumentType.CURRENT_STATE, "Já substituído.",
    )
    superseded.is_current = False
    db_session.flush()

    assert documents_historical(db_session, campaign.id) == [superseded]
    assert current not in documents_historical(db_session, campaign.id)


def test_documents_recent_respects_the_time_window(db_session):
    campaign = create_campaign(db_session, "Temporal Recente")
    recent = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.EVENT, "evt_recent",
        KnowledgeDocumentType.HISTORICAL_EVENT, "Aconteceu recentemente.",
        occurred_world_minute=950,
    )
    old = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.EVENT, "evt_old",
        KnowledgeDocumentType.HISTORICAL_EVENT, "Aconteceu há muito tempo.",
        occurred_world_minute=100,
    )
    timeless = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake",
        KnowledgeDocumentType.IDENTITY, "Geografia geral, sem data.",
    )

    results = documents_recent(db_session, campaign.id, current_world_minute=1000, within_minutes=100)

    assert results == [recent]
    assert old not in results
    assert timeless not in results


def test_documents_during_period_includes_historical_versions(db_session):
    campaign = create_campaign(db_session, "Temporal Periodo")
    inside = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.EVENT, "evt_inside",
        KnowledgeDocumentType.HISTORICAL_EVENT, "Dentro do período.",
        occurred_world_minute=500,
    )
    inside.is_current = False
    outside = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.EVENT, "evt_outside",
        KnowledgeDocumentType.HISTORICAL_EVENT, "Fora do período.",
        occurred_world_minute=2000,
    )
    db_session.flush()

    results = documents_during_period(db_session, campaign.id, start_minute=100, end_minute=1000)

    assert results == [inside]
    assert outside not in results


def test_documents_at_time_picks_the_version_in_effect_then(db_session):
    """The spec's own worked example: Osgar is blacksmith (Year 1), then
    Mira becomes blacksmith (Year 5). Querying an earlier moment must
    return Osgar; querying a later moment must return Mira — semantic
    similarity never decides this, only occurred_world_minute."""
    campaign = create_campaign(db_session, "Temporal Ponto No Tempo")
    osgar_version = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "cardal_blacksmith",
        KnowledgeDocumentType.CURRENT_STATE, "Osgar é o ferreiro de Cardal.",
        occurred_world_minute=100,
    )
    osgar_version.is_current = False
    db_session.flush()
    mira_version = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "cardal_blacksmith",
        KnowledgeDocumentType.CURRENT_STATE, "Mira é a ferreira de Cardal.",
        occurred_world_minute=500,
    )
    db_session.flush()

    assert documents_at_time(db_session, campaign.id, at_minute=200) == [osgar_version]
    assert documents_at_time(db_session, campaign.id, at_minute=600) == [mira_version]
    assert documents_at_time(db_session, campaign.id, at_minute=50) == []
