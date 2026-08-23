"""Phase 20L — Character Position & Navigation State."""

from app.core.enums import DiscoveryStatus, GeographicKnowledgeAspect, GeographicPrecision, KnowerType
from app.db.models.location import Location
from app.game.character.service import create_character
from app.game.discovery.service import set_location_discovery
from app.game.knowledge.geography import ensure_geographic_fact, geographic_fact_key, grant_fact_with_precision
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def test_position_is_precise_at_the_characters_current_visited_location(db_session):
    campaign = create_campaign(db_session, "Posicao Precisa Ao Chegar", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id)

    assert view.position_location_id == village.id
    assert view.position_precision == GeographicPrecision.PRECISE.value


def test_position_matches_the_current_locations_own_precision(db_session):
    """The character standing on a Location their own Map View only
    considers DISCOVERED (not VISITED) should get the same
    APPROXIMATE precision that location would show anyone else —
    position is never more certain than the location entry itself."""
    campaign = create_campaign(db_session, "Posicao Acompanha Precisao Do Local", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.DISCOVERED)
    character.location_id = village.id

    view = get_map_view(db_session, campaign.id, character.id)

    assert view.position_location_id == village.id
    assert view.position_precision == GeographicPrecision.APPROXIMATE.value


def test_position_prefers_a_precise_phase17_grant_over_the_fallback(db_session):
    campaign = create_campaign(db_session, "Posicao Prefere Grant Preciso", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.DISCOVERED)
    character.location_id = village.id
    ensure_geographic_fact(
        db_session, campaign.id, "location", village.id,
        GeographicKnowledgeAspect.ROUTE, "Conhece cada palmo do caminho até aqui.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", village.id, GeographicKnowledgeAspect.ROUTE),
        KnowerType.PLAYER, character.id, precision=GeographicPrecision.PRECISE,
    )

    view = get_map_view(db_session, campaign.id, character.id)

    assert view.position_precision == GeographicPrecision.PRECISE.value


def test_position_is_none_when_current_location_never_made_it_into_the_map_view(db_session):
    """No exact marker rather than lying about position."""
    campaign = create_campaign(db_session, "Posicao Desconhecida", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    elsewhere = Location(region_id=region.id, name="Lugar Nao Registrado", type="generic")
    db_session.add(elsewhere)
    db_session.flush()
    character.location_id = elsewhere.id
    # Nenhum sinal (descoberta/conhecimento/mapa/rumor) sobre `elsewhere`.

    view = get_map_view(db_session, campaign.id, character.id)

    assert view.position_location_id is None
    assert view.position_precision is None
