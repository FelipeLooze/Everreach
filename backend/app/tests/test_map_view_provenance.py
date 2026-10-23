"""Phase 20N — Cartography & Exploration Integration."""

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.knowledge.geography import ensure_geographic_fact, geographic_fact_key, grant_fact_with_precision
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

