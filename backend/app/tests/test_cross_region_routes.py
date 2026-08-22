"""Phase 16Q — Cross-Region World Connections."""

from app.game.travel.service import find_connection
from app.game.world.boundaries import create_regional_boundary, get_boundary_routes
from app.game.world.cross_region_routes import connect_boundary_to_neighbor_region
from app.game.world.neighbor_region import materialize_neighbor_region
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Ligacao {world_seed}", world_seed=world_seed)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)
    return campaign, source_region, boundary, neighbor


def test_connecting_sets_destination_region_on_the_boundary(db_session):
    _campaign, _source, boundary, neighbor = _setup(db_session, 400)

    entry = connect_boundary_to_neighbor_region(db_session, boundary, neighbor)

    assert boundary.destination_region_id == neighbor.id
    assert entry.region_id == neighbor.id


def test_the_safest_public_route_becomes_a_real_bidirectional_connection(db_session):
    _campaign, _source, boundary, neighbor = _setup(db_session, 401)

    entry = connect_boundary_to_neighbor_region(db_session, boundary, neighbor)
    routes = get_boundary_routes(db_session, boundary.id)
    public_routes = [r for r in routes if r.is_publicly_known]
    primary_route = min(public_routes, key=lambda r: r.danger_hint)

    assert primary_route.destination_location_id == entry.id

    outward = find_connection(db_session, primary_route.origin_location_id, entry.id)
    assert outward is not None
    assert outward.distance == primary_route.estimated_distance
    assert outward.danger == primary_route.danger_hint

    inward = find_connection(db_session, entry.id, primary_route.origin_location_id)
    assert inward is not None

    # Every other route stays a real, distinct, discoverable BoundaryRoute
    # — just not (yet) its own separate walkable graph edge.
    for route in routes:
        if route.id != primary_route.id:
            assert route.destination_location_id is None


def test_the_frontier_is_now_actually_reachable_into_the_neighbor_via_travel_graph(db_session):
    import random

    from app.db.models.location import CharacterConnectionDiscovery
    from app.game.character.service import create_character
    from app.game.travel.service import move_character

    campaign, source_region, boundary, neighbor = _setup(db_session, 402)
    connect_boundary_to_neighbor_region(db_session, boundary, neighbor)

    character = create_character(
        db_session, campaign.id, "Logan", region_id=source_region.id, location_id=boundary.frontier_location_id
    )

    public_routes = [r for r in get_boundary_routes(db_session, boundary.id) if r.is_publicly_known]
    route = min(public_routes, key=lambda r: r.danger_hint)

    connection = find_connection(db_session, boundary.frontier_location_id, route.destination_location_id)
    db_session.add(CharacterConnectionDiscovery(character_id=character.id, connection_id=connection.id))
    # A cross-region route is a genuinely massive distance (spec: this
    # should be a major expedition) — bump stamina so this test isolates
    # graph reachability from the (correctly) separate stamina-budget
    # mechanic.
    character.stamina_current = 100000.0
    character.stamina_max = 100000.0
    db_session.flush()

    move_character(
        db_session, campaign.id, character, route.destination_location_id, rng=random.Random(0)
    )

    assert character.location_id == route.destination_location_id
    assert character.region_id == neighbor.id
