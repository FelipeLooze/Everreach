"""Phase 18G — Geographic / Regional Knowledge Retrieval."""

from app.ai.retrieval.canon import index_region, index_settlement
from app.ai.retrieval.geography import geographic_documents_known_to
from app.core.enums import GeographicKnowledgeAspect, KnowerType
from app.db.models.settlement import Settlement
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.world.seed import create_campaign, seed_initial_region


def test_knower_without_any_geographic_knowledge_gets_nothing(db_session):
    campaign = create_campaign(db_session, "Sem Conhecimento Geografico", world_seed=1)
    region, _village = seed_initial_region(db_session, campaign.id)
    index_region(db_session, region)

    assert geographic_documents_known_to(
        db_session, campaign.id, KnowerType.PLAYER, "char_fake"
    ) == []


def test_knower_only_sees_regions_it_has_a_knowledge_grant_for(db_session):
    campaign = create_campaign(db_session, "Conhecimento Concedido", world_seed=2)
    region, _village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan")
    index_region(db_session, region)

    ensure_geographic_fact(
        db_session, campaign.id, "region", region.id,
        GeographicKnowledgeAspect.EXISTENCE, f"{region.name} existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, character.id,
        "region", region.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    documents = geographic_documents_known_to(db_session, campaign.id, KnowerType.PLAYER, character.id)

    # index_region produces both an IDENTITY and a BACKGROUND document for
    # the same region (Phase 18B) — a single Knowledge grant on the
    # region's subject admits both, since both share the same source_id.
    assert documents
    assert {document.source_id for document in documents} == {region.id}


def test_a_semantically_relevant_but_unknown_settlement_is_never_returned(db_session):
    """Spec's own worked example, shape-for-shape: a document existing in
    the index (18B) never implies a specific knower may see it — the
    tunnel Mira does not know about must never leak just because it is
    indexed."""
    campaign = create_campaign(db_session, "Assentamento Nao Conhecido", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    settlement = db_session.query(Settlement).filter(Settlement.location_id == village.id).one()
    character = create_character(db_session, campaign.id, "Logan")
    index_settlement(db_session, settlement)

    documents = geographic_documents_known_to(db_session, campaign.id, KnowerType.PLAYER, character.id)

    assert documents == []


def test_different_knowers_see_different_geographic_documents(db_session):
    campaign = create_campaign(db_session, "Conhecimento Por Personagem", world_seed=4)
    region, _village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan")
    mira = create_character(db_session, campaign.id, "Mira")
    index_region(db_session, region)

    ensure_geographic_fact(
        db_session, campaign.id, "region", region.id,
        GeographicKnowledgeAspect.EXISTENCE, f"{region.name} existe.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "region", region.id, GeographicKnowledgeAspect.EXISTENCE,
    )

    assert geographic_documents_known_to(db_session, campaign.id, KnowerType.PLAYER, logan.id)
    assert geographic_documents_known_to(db_session, campaign.id, KnowerType.PLAYER, mira.id) == []
