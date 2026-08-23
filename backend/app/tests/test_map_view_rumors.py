"""Phase 20H — Rumors & Unconfirmed Locations."""

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType, RumorAccuracy
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.knowledge.rumors import establish_rumor, grant_rumor
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def test_a_rumored_location_appears_marked_as_a_rumor(db_session):
    campaign = create_campaign(db_session, "Rumor De Existencia", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    ruins = Location(region_id=region.id, name="Ruinas Antigas", type="generic", x=77, y=88)
    db_session.add(ruins)
    db_session.flush()

    establish_rumor(
        db_session, campaign.id, "location", ruins.id, GeographicKnowledgeAspect.EXISTENCE,
        "cacador_1", "Ha ruinas antigas a oeste do bosque.", RumorAccuracy.TRUE,
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, character.id, "location", ruins.id,
        GeographicKnowledgeAspect.EXISTENCE, "cacador_1", source="npc:cacador_1",
    )

    view = get_map_view(db_session, campaign.id, character.id)

    location = next((item for item in view.locations if item.id == ruins.id), None)
    assert location is not None
    assert location.source == "rumor"


def test_a_rumor_never_reveals_the_exact_authoritative_position(db_session):
    campaign = create_campaign(db_session, "Rumor Nunca Vaza Posicao", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    ruins = Location(region_id=region.id, name="Torre Ruina", type="generic", x=12345, y=6789)
    db_session.add(ruins)
    db_session.flush()

    establish_rumor(
        db_session, campaign.id, "location", ruins.id, GeographicKnowledgeAspect.EXISTENCE,
        "viajante_1", "Ha uma torre em ruinas ao norte.", RumorAccuracy.FALSE,
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, character.id, "location", ruins.id,
        GeographicKnowledgeAspect.EXISTENCE, "viajante_1", source="npc:viajante_1",
        precision=GeographicPrecision.PRECISE,
    )

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == ruins.id)
    assert location.x is None
    assert location.y is None


def test_a_location_with_no_rumor_and_no_other_signal_never_appears(db_session):
    campaign = create_campaign(db_session, "Sem Rumor Nenhum", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    hidden = Location(region_id=region.id, name="Nunca Ouvido Falar", type="generic")
    db_session.add(hidden)
    db_session.flush()

    view = get_map_view(db_session, campaign.id, character.id)

    assert all(item.id != hidden.id for item in view.locations)


def test_a_confirmed_grant_takes_precedence_over_a_rumor_for_the_same_location(db_session):
    from app.game.knowledge.geography import ensure_geographic_fact, geographic_fact_key, grant_fact_with_precision

    campaign = create_campaign(db_session, "Confirmado Tem Prioridade Sobre Rumor", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    place = Location(region_id=region.id, name="Vilarejo Rowan", type="settlement", x=1, y=1)
    db_session.add(place)
    db_session.flush()

    establish_rumor(
        db_session, campaign.id, "location", place.id, GeographicKnowledgeAspect.EXISTENCE,
        "rumor_1", "Um lugar existe por ali.", RumorAccuracy.TRUE,
    )
    grant_rumor(
        db_session, campaign.id, KnowerType.PLAYER, character.id, "location", place.id,
        GeographicKnowledgeAspect.EXISTENCE, "rumor_1", source="npc:x",
    )
    ensure_geographic_fact(
        db_session, campaign.id, "location", place.id,
        GeographicKnowledgeAspect.EXISTENCE, "Um lugar existe por ali, confirmado.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", place.id, GeographicKnowledgeAspect.EXISTENCE),
        KnowerType.PLAYER, character.id, precision=GeographicPrecision.VAGUE,
    )

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == place.id)
    assert location.source == "knowledge"
