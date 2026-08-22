"""Phase 17F — Cartography Foundation."""

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, KnowledgeCertainty, RumorAccuracy
from app.game.character.service import create_character
from app.game.knowledge.cartography import survey_cartographic_knowledge
from app.game.knowledge.geography import ensure_geographic_fact, grant_geographic_knowledge
from app.game.knowledge.rumors import establish_rumor, grant_rumor
from app.game.world.seed import create_campaign


def test_no_knowledge_means_no_map_possible(db_session):
    campaign = create_campaign(db_session, "Sem Conhecimento Mapa", world_seed=1)
    logan = create_character(db_session, campaign.id, "Logan")

    survey = survey_cartographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_never_taught"
    )

    assert survey.aspects == []
    assert survey.can_produce_map is False


def test_existence_alone_is_not_enough_to_map(db_session):
    campaign = create_campaign(db_session, "So Existencia", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE,
        "Uma grande cidade existe em algum lugar.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE,
    )

    survey = survey_cartographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven"
    )
    assert survey.can_produce_map is False


def test_existence_plus_a_spatial_aspect_allows_a_map(db_session):
    campaign = create_campaign(db_session, "Existencia Mais Direcao", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")

    for aspect, statement in [
        (GeographicKnowledgeAspect.EXISTENCE, "Uma grande cidade existe ao sul."),
        (GeographicKnowledgeAspect.DIRECTION, "Fica ao sul de Cardal."),
    ]:
        ensure_geographic_fact(db_session, campaign.id, "settlement", "loc_arven", aspect, statement)
        grant_geographic_knowledge(
            db_session, campaign.id, KnowerType.PLAYER, logan.id,
            "settlement", "loc_arven", aspect, precision=GeographicPrecision.APPROXIMATE,
        )

    survey = survey_cartographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven"
    )
    assert survey.can_produce_map is True
    assert len(survey.aspects) == 2
    surveyed_direction = next(a for a in survey.aspects if a.aspect == GeographicKnowledgeAspect.DIRECTION)
    assert surveyed_direction.statement == "Fica ao sul de Cardal."
    assert surveyed_direction.precision == GeographicPrecision.APPROXIMATE


def test_survey_is_scoped_per_knower(db_session):
    campaign = create_campaign(db_session, "Levantamento Individual", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")
    npc_id = "npc_cartographer_test"

    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE, "Existe uma cidade.",
    )
    ensure_geographic_fact(
        db_session, campaign.id, "settlement", "loc_arven", GeographicKnowledgeAspect.DISTANCE, "Fica a duas semanas.",
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc_id, "settlement", "loc_arven", GeographicKnowledgeAspect.EXISTENCE,
    )
    grant_geographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc_id, "settlement", "loc_arven", GeographicKnowledgeAspect.DISTANCE,
    )

    npc_survey = survey_cartographic_knowledge(
        db_session, campaign.id, KnowerType.NPC, npc_id, "settlement", "loc_arven"
    )
    logan_survey = survey_cartographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "settlement", "loc_arven"
    )

    assert npc_survey.can_produce_map is True
    assert logan_survey.can_produce_map is False
    assert logan_survey.aspects == []


def test_rumors_about_the_entity_are_included_in_the_survey(db_session):
    campaign = create_campaign(db_session, "Levantamento Com Rumor", world_seed=5)
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

    survey = survey_cartographic_knowledge(
        db_session, campaign.id, KnowerType.PLAYER, logan.id, "boundary", "bound_x"
    )

    assert survey.can_produce_map is True
    route_entries = [a for a in survey.aspects if a.aspect == GeographicKnowledgeAspect.ROUTE]
    assert len(route_entries) == 1
    assert route_entries[0].certainty == KnowledgeCertainty.RUMOR.value
