"""Phase 20N — Cartography & Exploration Integration."""

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType, RumorAccuracy
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.knowledge.geography import ensure_geographic_fact, geographic_fact_key, grant_fact_with_precision
from app.game.knowledge.maps import create_map
from app.game.knowledge.rumors import establish_rumor, grant_rumor
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def test_discovery_sourced_location_shows_physical_presence_as_provenance(db_session):
    campaign = create_campaign(db_session, "Provenance Presenca Fisica", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id)

    location = next(item for item in view.locations if item.id == village.id)
    assert location.provenance == "presença física"


def test_map_sourced_location_shows_physical_map_as_provenance(db_session):
    campaign = create_campaign(db_session, "Provenance Mapa Fisico", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    cartographer = create_character(db_session, campaign.id, "Mira", region.id, village.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    place = Location(region_id=region.id, name="Rowan", type="settlement", x=1, y=1)
    db_session.add(place)
    db_session.flush()
    ensure_geographic_fact(
        db_session, campaign.id, "location", place.id,
        GeographicKnowledgeAspect.EXISTENCE, "Um povoado existe.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", place.id, GeographicKnowledgeAspect.EXISTENCE),
        KnowerType.PLAYER, cartographer.id, precision=GeographicPrecision.VAGUE,
    )
    ensure_geographic_fact(
        db_session, campaign.id, "location", place.id,
        GeographicKnowledgeAspect.DIRECTION, "Fica a leste.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", place.id, GeographicKnowledgeAspect.DIRECTION),
        KnowerType.PLAYER, cartographer.id, precision=GeographicPrecision.GOOD,
    )
    instance, map_row = create_map(db_session, campaign.id, cartographer.id, "location", place.id)
    instance.owner_ref = logan.id
    db_session.flush()

    view = get_map_view(db_session, campaign.id, logan.id)

    location = next(item for item in view.locations if item.id == place.id)
    assert location.provenance == "mapa físico"
