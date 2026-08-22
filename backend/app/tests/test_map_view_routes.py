"""Phase 20F — Known Routes & Connections."""

from app.core.enums import DiscoveryStatus
from app.db.models.location import Location, LocationConnection
from app.game.character.service import create_character
from app.game.discovery.service import discover_connection, set_location_discovery
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def _add_connection(db_session, from_location, to_location, **kwargs):
    connection = LocationConnection(
        from_location_id=from_location.id,
        to_location_id=to_location.id,
        **kwargs,
    )
    db_session.add(connection)
    db_session.flush()
    return connection


def test_knowing_both_endpoints_does_not_imply_knowing_the_route(db_session):
    campaign = create_campaign(db_session, "Rota Sem Conexao Conhecida", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    other = Location(region_id=region.id, name="Arven", type="settlement", x=10, y=10)
    db_session.add(other)
    db_session.flush()
    _add_connection(db_session, village, other, direction="sul", distance=5.0, danger=1)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, other.id, DiscoveryStatus.DISCOVERED)
    # Nunca chamamos discover_connection.

    view = get_map_view(db_session, campaign.id, character.id)

    assert view.routes == []


def test_known_connection_appears_as_a_route(db_session):
    campaign = create_campaign(db_session, "Rota Conhecida", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    other = Location(region_id=region.id, name="Arven", type="settlement", x=10, y=10)
    db_session.add(other)
    db_session.flush()
    connection = _add_connection(db_session, village, other, direction="sul", distance=5.0, danger=1)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, other.id, DiscoveryStatus.DISCOVERED)
    discover_connection(db_session, character.id, connection.id)

    view = get_map_view(db_session, campaign.id, character.id)

    assert len(view.routes) == 1
    route = view.routes[0]
    assert route.from_location_id == village.id
    assert route.to_location_id == other.id
    assert route.direction == "sul"
    assert route.distance == 5.0
    assert route.danger == 1


def test_route_excluded_when_scope_removes_one_endpoint(db_session):
    campaign = create_campaign(db_session, "Rota Fora De Escopo", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    other = Location(region_id=region.id, name="Arven", type="settlement", x=10, y=10)
    db_session.add(other)
    db_session.flush()
    connection = _add_connection(db_session, village, other, direction="sul", distance=5.0, danger=0)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, other.id, DiscoveryStatus.DISCOVERED)
    discover_connection(db_session, character.id, connection.id)

    view = get_map_view(db_session, campaign.id, character.id, scope="world")

    assert view.routes == []


def test_route_never_leaks_a_connection_to_an_unknown_location(db_session):
    campaign = create_campaign(db_session, "Rota Nao Vaza Destino", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    hidden = Location(region_id=region.id, name="Local Oculto", type="generic")
    db_session.add(hidden)
    db_session.flush()
    connection = _add_connection(db_session, village, hidden, distance=1.0)
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    # `hidden` nunca é descoberto pelo personagem.
    discover_connection(db_session, character.id, connection.id)

    view = get_map_view(db_session, campaign.id, character.id)

    assert view.routes == []
    assert all(location.id != hidden.id for location in view.locations)
