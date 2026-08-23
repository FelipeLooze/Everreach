"""Phase 20K — Dynamic World Changes & Stale Knowledge."""

from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.knowledge.geography import (
    ensure_geographic_fact,
    geographic_fact_key,
    grant_fact_with_precision,
    update_geographic_fact_statement,
)
from app.game.knowledge.maps import create_map
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def _grant(db_session, campaign_id, character_id, location_id, aspect, statement, precision):
    ensure_geographic_fact(db_session, campaign_id, "location", location_id, aspect, statement)
    grant_fact_with_precision(
        db_session, campaign_id,
        geographic_fact_key("location", location_id, aspect),
        KnowerType.PLAYER, character_id, precision=precision,
    )


def test_a_map_whose_world_truth_changed_since_creation_is_flagged_stale(db_session):
    campaign = create_campaign(db_session, "Mapa Fica Desatualizado", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    cartographer = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    bridge_town = Location(region_id=region.id, name="Vau da Ponte", type="settlement", x=5, y=5)
    db_session.add(bridge_town)
    db_session.flush()

    _grant(
        db_session, campaign.id, cartographer.id, bridge_town.id,
        GeographicKnowledgeAspect.EXISTENCE, "Um povoado existe perto de uma ponte.", GeographicPrecision.VAGUE,
    )
    _grant(
        db_session, campaign.id, cartographer.id, bridge_town.id,
        GeographicKnowledgeAspect.DISTANCE, "A ponte de pedra permite a travessia.", GeographicPrecision.GOOD,
    )
    instance, map_row = create_map(db_session, campaign.id, cartographer.id, "location", bridge_town.id)
    instance.owner_ref = logan.id
    db_session.flush()

    # O mundo muda depois que o mapa foi desenhado: a ponte caiu.
    update_geographic_fact_statement(
        db_session, campaign.id, "location", bridge_town.id,
        GeographicKnowledgeAspect.DISTANCE, "A ponte de pedra desmoronou; não há mais travessia.",
    )

    view = get_map_view(db_session, campaign.id, logan.id)

    location = next(item for item in view.locations if item.id == bridge_town.id)
    assert location.source == "map"
    assert location.stale is True


def test_a_map_whose_world_truth_never_changed_is_not_stale(db_session):
    campaign = create_campaign(db_session, "Mapa Continua Atualizado", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    cartographer = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    place = Location(region_id=region.id, name="Rowan", type="settlement", x=1, y=1)
    db_session.add(place)
    db_session.flush()

    _grant(
        db_session, campaign.id, cartographer.id, place.id,
        GeographicKnowledgeAspect.EXISTENCE, "Um povoado existe.", GeographicPrecision.VAGUE,
    )
    _grant(
        db_session, campaign.id, cartographer.id, place.id,
        GeographicKnowledgeAspect.DIRECTION, "Fica a leste.", GeographicPrecision.GOOD,
    )
    instance, map_row = create_map(db_session, campaign.id, cartographer.id, "location", place.id)
    instance.owner_ref = logan.id
    db_session.flush()

    view = get_map_view(db_session, campaign.id, logan.id)

    location = next(item for item in view.locations if item.id == place.id)
    assert location.stale is False


def test_non_map_sourced_locations_are_never_marked_stale(db_session):
    from app.core.enums import DiscoveryStatus
    from app.game.discovery.service import set_location_discovery

    campaign = create_campaign(db_session, "Descoberta Nunca Fica Desatualizada", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == village.id)
    assert location.source == "discovery"
    assert location.stale is False
