"""Phase 17B — Geographic Information Precision."""

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty
from app.game.character.service import create_character
from app.game.knowledge.geography import (
    ensure_geographic_fact,
    geographic_knowledge_precision,
    grant_geographic_knowledge,
)
from app.game.world.seed import create_campaign


def test_first_grant_defaults_to_vague(db_session):
    campaign = create_campaign(db_session, "Precisao Default", world_seed=1)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.DIRECTION,
        "Fica ao sul.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.DIRECTION,
    )

    precision = geographic_knowledge_precision(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven", GeographicKnowledgeAspect.DIRECTION
    )
    assert precision == GeographicPrecision.VAGUE


def test_precision_upgrades_monotonically(db_session):
    campaign = create_campaign(db_session, "Precisao Sobe", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.DISTANCE,
        "Fica a algumas semanas de distância.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.DISTANCE,
        precision=GeographicPrecision.VAGUE,
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.DISTANCE,
        precision=GeographicPrecision.GOOD,
    )

    precision = geographic_knowledge_precision(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven", GeographicKnowledgeAspect.DISTANCE
    )
    assert precision == GeographicPrecision.GOOD


def test_precision_never_downgrades(db_session):
    campaign = create_campaign(db_session, "Precisao Nao Cai", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE,
        "Siga a estrada principal para o sul.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE,
        precision=GeographicPrecision.PRECISE,
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE,
        precision=GeographicPrecision.VAGUE,
    )

    precision = geographic_knowledge_precision(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven", GeographicKnowledgeAspect.ROUTE
    )
    assert precision == GeographicPrecision.PRECISE


def test_precision_and_certainty_are_independent_axes(db_session):
    campaign = create_campaign(db_session, "Eixos Independentes", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "boundary_route", "route_x", GeographicKnowledgeAspect.DESCRIPTION,
        "Um velho mapa detalhado mostra a rota exata, mas pode estar desatualizado.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "boundary_route", "route_x", GeographicKnowledgeAspect.DESCRIPTION,
        certainty=KnowledgeCertainty.RUMOR,
        precision=GeographicPrecision.PRECISE,
    )

    from app.game.knowledge.geography import geographic_fact_key
    from app.db.models.knowledge import KnowledgeFact, KnowledgeKnower

    fact_key = geographic_fact_key("boundary_route", "route_x", GeographicKnowledgeAspect.DESCRIPTION)
    fact = db_session.query(KnowledgeFact).filter(KnowledgeFact.fact_key == fact_key).one()
    knower = (
        db_session.query(KnowledgeKnower)
        .filter(KnowledgeKnower.fact_id == fact.id, KnowledgeKnower.knower_id == logan.id)
        .one()
    )
    # Highly precise information the character barely trusts — the two
    # axes must not contaminate each other.
    assert knower.certainty == KnowledgeCertainty.RUMOR.value
    assert knower.precision == GeographicPrecision.PRECISE.value


def test_unknown_aspect_has_no_precision(db_session):
    campaign = create_campaign(db_session, "Sem Conhecimento", world_seed=5)
    logan = create_character(db_session, campaign.id, "Logan")

    precision = geographic_knowledge_precision(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_never_taught", GeographicKnowledgeAspect.NAME
    )
    assert precision is None
