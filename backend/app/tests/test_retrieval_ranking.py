"""Phase 18K — Hybrid Ranking & Relevance."""

from app.ai.retrieval.canon import index_region
from app.ai.retrieval.documents import upsert_document
from app.ai.retrieval.ranking import DEFAULT_WEIGHTS, rank_documents
from app.ai.retrieval.semantic import ScoredDocument
from app.core.enums import GeographicKnowledgeAspect, KnowerType, KnowledgeDocumentType, KnowledgeSourceType
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.world.seed import create_campaign, seed_initial_region


def _grant_region(db_session, campaign_id, region, character_id):
    ensure_geographic_fact(
        db_session, campaign_id, "region", region.id,
        GeographicKnowledgeAspect.EXISTENCE, "Existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign_id, KnowerType.PLAYER, character_id,
        "region", region.id, GeographicKnowledgeAspect.EXISTENCE,
    )


def test_an_inaccessible_document_is_dropped_even_with_a_perfect_semantic_score(db_session):
    campaign = create_campaign(db_session, "Ranking Filtro Duro", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan")
    document = index_region(db_session, region)
    # Nenhum grant de Knowledge concedido — o personagem não conhece a região.

    results = rank_documents(
        db_session, campaign.id, [ScoredDocument(document, 1.0)],
        KnowerType.PLAYER, character.id,
    )

    assert results == []


def test_accessible_document_with_higher_semantic_score_ranks_first(db_session):
    campaign = create_campaign(db_session, "Ranking Semantico", world_seed=2)
    region, _village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan")
    _grant_region(db_session, campaign.id, region, character.id)
    strong = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, region.id,
        KnowledgeDocumentType.IDENTITY, "Documento muito relevante.",
    )
    weak = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, region.id,
        KnowledgeDocumentType.BACKGROUND, "Documento pouco relevante.",
    )

    results = rank_documents(
        db_session, campaign.id,
        [ScoredDocument(weak, 0.1), ScoredDocument(strong, 0.9)],
        KnowerType.PLAYER, character.id,
    )

    assert [ranked.document.id for ranked in results] == [strong.id, weak.id]


def test_entity_match_can_outrank_a_higher_raw_semantic_score(db_session):
    campaign = create_campaign(db_session, "Ranking Entidade")
    character = create_character(db_session, campaign.id, "Logan")
    for region_id in ("region_in_scene", "region_out_of_scene"):
        ensure_geographic_fact(
            db_session, campaign.id, "region", region_id,
            GeographicKnowledgeAspect.EXISTENCE, "Existe.",
        )
        grant_geographic_knowledge(
            db_session, campaign.id, KnowerType.PLAYER, character.id,
            "region", region_id, GeographicKnowledgeAspect.EXISTENCE,
        )
    in_scene = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_in_scene",
        KnowledgeDocumentType.IDENTITY, "Cena atual.",
    )
    out_of_scene = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_out_of_scene",
        KnowledgeDocumentType.IDENTITY, "Fora de cena.",
    )

    results = rank_documents(
        db_session, campaign.id,
        [ScoredDocument(out_of_scene, 0.6), ScoredDocument(in_scene, 0.55)],
        KnowerType.PLAYER, character.id,
        scene_subjects=["region:region_in_scene"],
    )

    assert results[0].document.id == in_scene.id
    assert results[0].entity_match is True
    assert results[1].entity_match is False


def test_importance_score_uses_the_events_stored_importance(db_session):
    """EVENT source_type has no established access story yet (Phase 18I),
    so this exercises the importance signal via two REGION documents
    with document_type=HISTORICAL_EVENT — the scoring function keys off
    document_type + source_version alone, independent of source_type."""
    campaign = create_campaign(db_session, "Ranking Importancia")
    character = create_character(db_session, campaign.id, "Logan")
    for region_id in ("region_major", "region_minor"):
        ensure_geographic_fact(
            db_session, campaign.id, "region", region_id,
            GeographicKnowledgeAspect.EXISTENCE, "Existe.",
        )
        grant_geographic_knowledge(
            db_session, campaign.id, KnowerType.PLAYER, character.id,
            "region", region_id, GeographicKnowledgeAspect.EXISTENCE,
        )
    major = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_major",
        KnowledgeDocumentType.HISTORICAL_EVENT, "Evento muito importante.",
        source_version="5",
    )
    minor = upsert_document(
        db_session, campaign.id, KnowledgeSourceType.REGION, "region_minor",
        KnowledgeDocumentType.HISTORICAL_EVENT, "Evento pouco importante.",
        source_version="3",
    )

    results = rank_documents(
        db_session, campaign.id,
        [ScoredDocument(minor, 0.5), ScoredDocument(major, 0.5)],
        KnowerType.PLAYER, character.id,
    )

    assert results[0].document.id == major.id
    assert results[0].importance_score == 1.0
    assert results[1].importance_score == 0.6


def test_default_weights_sum_is_stable_and_documented():
    assert set(DEFAULT_WEIGHTS) == {"semantic", "entity_match", "recency", "importance"}
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9
