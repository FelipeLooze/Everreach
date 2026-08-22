"""Phase 17H — Map Accuracy, Age & Reliability."""

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty, RumorAccuracy
from app.game.character.service import create_character
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge, update_geographic_fact_statement
from app.game.knowledge.map_reliability import (
    find_outdated_map_aspects,
    map_age_minutes,
    map_reliability_certainty,
    map_reliability_precision,
)
from app.game.knowledge.maps import create_map
from app.game.knowledge.rumors import establish_rumor, grant_rumor
from app.game.time.clock import advance_world_time
from app.game.world.seed import create_campaign


def _grant_mixed_knowledge(db_session, campaign_id, character_id, subject_kind, entity_id):
    ensure_geographic_fact(
        db_session, campaign_id, subject_kind, entity_id, GeographicKnowledgeAspect.EXISTENCE,
        "Uma grande cidade existe ao sul.",
    )
    grant_geographic_knowledge(
        db_session, campaign_id, KnowerType.PLAYER, character_id, subject_kind, entity_id,
        GeographicKnowledgeAspect.EXISTENCE, precision=GeographicPrecision.PRECISE,
        certainty=KnowledgeCertainty.CONFIRMED,
    )
    ensure_geographic_fact(
        db_session, campaign_id, subject_kind, entity_id, GeographicKnowledgeAspect.DIRECTION,
        "Fica ao sul de Cardal.",
    )
    grant_geographic_knowledge(
        db_session, campaign_id, KnowerType.PLAYER, character_id, subject_kind, entity_id,
        GeographicKnowledgeAspect.DIRECTION, precision=GeographicPrecision.VAGUE,
        certainty=KnowledgeCertainty.BELIEVED,
    )


def test_map_age_advances_with_world_time(db_session):
    campaign = create_campaign(db_session, "Idade Do Mapa", world_seed=1)
    logan = create_character(db_session, campaign.id, "Logan")
    _grant_mixed_knowledge(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    _instance, map_row = create_map(db_session, campaign.id, logan.id, "settlement", "loc_arven")
    assert map_age_minutes(db_session, campaign.id, map_row) == 0

    advance_world_time(db_session, campaign.id, 60 * 24 * 10)
    assert map_age_minutes(db_session, campaign.id, map_row) == 60 * 24 * 10


def test_reliability_is_the_worst_recorded_aspect(db_session):
    campaign = create_campaign(db_session, "Confiabilidade Pior Caso", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")
    _grant_mixed_knowledge(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    _instance, map_row = create_map(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    assert map_reliability_precision(map_row) == GeographicPrecision.VAGUE
    assert map_reliability_certainty(map_row) == KnowledgeCertainty.BELIEVED


def test_nothing_is_outdated_right_after_creation(db_session):
    campaign = create_campaign(db_session, "Nada Desatualizado", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")
    _grant_mixed_knowledge(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    _instance, map_row = create_map(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    assert find_outdated_map_aspects(db_session, campaign.id, map_row) == set()


def test_updating_world_truth_makes_the_map_outdated_for_that_aspect_only(db_session):
    """Bridge of Hal example: a map still shows what was true when it
    was drawn, even after the world changes."""
    campaign = create_campaign(db_session, "Ponte De Hal", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")
    _grant_mixed_knowledge(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    _instance, map_row = create_map(db_session, campaign.id, logan.id, "settlement", "loc_arven")

    update_geographic_fact_statement(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.DIRECTION,
        "A antiga ponte ao sul desabou; o caminho agora é outro.",
    )

    outdated = find_outdated_map_aspects(db_session, campaign.id, map_row)
    assert outdated == {GeographicKnowledgeAspect.DIRECTION}


def test_rumor_sourced_aspects_are_never_flagged_outdated(db_session):
    campaign = create_campaign(db_session, "Rumor No Mapa", world_seed=5)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "boundary", "bound_x", GeographicKnowledgeAspect.EXISTENCE, "Existe uma fronteira.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_x", GeographicKnowledgeAspect.EXISTENCE,
    )
    establish_rumor(
        db_session, campaign.id, "boundary", "bound_x", GeographicKnowledgeAspect.ROUTE, "traveler",
        "Dizem que há uma passagem secreta.",
        RumorAccuracy.OUTDATED,
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "boundary", "bound_x", GeographicKnowledgeAspect.ROUTE, "traveler",
        source="viajante",
    )

    _instance, map_row = create_map(db_session, campaign.id, logan.id, "boundary", "bound_x")

    assert find_outdated_map_aspects(db_session, campaign.id, map_row) == set()
