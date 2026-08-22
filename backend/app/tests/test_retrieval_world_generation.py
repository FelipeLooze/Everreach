"""Phase 18R — World Generator Retrieval."""

from app.ai.retrieval.canon import index_region
from app.ai.retrieval.documents import upsert_document
from app.ai.retrieval.world_generation import build_world_generation_context
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.game.world.seed import create_campaign, seed_initial_region


def test_world_generation_context_includes_canon_with_no_knowledge_gating(db_session):
    """Unlike every knower-scoped consumer, this must NEVER require a
    Knowledge grant — the World Generator needs full Canon visibility
    for consistency, not a character's limited perspective."""
    campaign = create_campaign(db_session, "Geracao De Mundo Sem Gate", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    index_region(db_session, region)
    # Nenhum KnowledgeFact/grant concedido a ninguém sobre esta região.

    context = build_world_generation_context(db_session, campaign.id)

    assert region.name in context


def test_world_generation_context_ranks_entity_matches_first(db_session):
    campaign = create_campaign(db_session, "Geracao De Mundo Ranking", world_seed=2)
    relevant = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_relevante",
        KnowledgeDocumentType.IDENTITY, "Uma região relevante para a fronteira leste.",
    )
    irrelevant = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_irrelevante",
        KnowledgeDocumentType.IDENTITY, "Uma região distante sem relação com a fronteira leste.",
    )

    context = build_world_generation_context(
        db_session, campaign.id, scene_subjects=["region:region_relevante"],
    )

    relevant_index = context.find("Uma região relevante")
    irrelevant_index = context.find("Uma região distante")
    assert relevant_index != -1
    assert irrelevant_index != -1
    assert relevant_index < irrelevant_index


def test_world_generation_context_respects_source_type_filter(db_session):
    campaign = create_campaign(db_session, "Geracao De Mundo Filtro De Tipo", world_seed=3)
    upsert_document(
        db_session, campaign.id, KnowledgeSourceType.NPC, "npc_fake",
        KnowledgeDocumentType.IDENTITY, "Um NPC irrelevante para geografia.",
    )
    region_document = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_fake",
        KnowledgeDocumentType.IDENTITY, "Uma região relevante.",
    )

    context = build_world_generation_context(
        db_session, campaign.id, near_source_types=[KnowledgeSourceType.REGION],
    )

    assert "Uma região relevante" in context
    assert "Um NPC irrelevante" not in context


def test_world_generation_context_empty_when_no_canon_exists(db_session):
    campaign = create_campaign(db_session, "Geracao De Mundo Sem Canon")

    context = build_world_generation_context(db_session, campaign.id)

    assert context == "EXISTING CANON\n- none recalled"
