"""Phase 20M — Travel Planning Integration."""

from app.core.enums import DiscoveryStatus
from app.db.models.location import Location, LocationConnection
from app.game.character.service import create_character
from app.game.discovery.service import discover_connection, set_location_discovery
from app.game.map.planning import plan_known_route
from app.game.world.seed import create_campaign, seed_initial_region


def _connect(db_session, from_location, to_location, **kwargs):
    connection = LocationConnection(from_location_id=from_location.id, to_location_id=to_location.id, **kwargs)
    db_session.add(connection)
    db_session.flush()
    return connection


def _know_location(db_session, character_id, location):
    set_location_discovery(db_session, character_id, location.id, DiscoveryStatus.VISITED)


def test_plan_finds_a_multi_hop_known_route(db_session):
    campaign = create_campaign(db_session, "Rota Multi Trecho", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    rowan = Location(region_id=region.id, name="Rowan", type="settlement", x=1, y=1)
    arven = Location(region_id=region.id, name="Arven", type="settlement", x=2, y=2)
    db_session.add_all([rowan, arven])
    db_session.flush()

    leg1 = _connect(db_session, village, rowan, distance=5.0, danger=0, travel_time_modifier=1.0)
    leg2 = _connect(db_session, rowan, arven, distance=7.0, danger=2, travel_time_modifier=1.2)

    for location in (village, rowan, arven):
        _know_location(db_session, character.id, location)
    discover_connection(db_session, character.id, leg1.id)
    discover_connection(db_session, character.id, leg2.id)

    plan = plan_known_route(db_session, campaign.id, character.id, village.id, arven.id)

    assert plan is not None
    assert [segment.to_location_id for segment in plan.segments] == [rowan.id, arven.id]
    assert plan.total_distance == 12.0
    assert plan.max_danger == 2
    assert plan.estimated_minutes > 0


def test_plan_returns_none_when_endpoints_are_known_but_no_route_connects_them(db_session):
    campaign = create_campaign(db_session, "Sem Rota Conhecida", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    arven = Location(region_id=region.id, name="Arven", type="settlement", x=2, y=2)
    db_session.add(arven)
    db_session.flush()
    # Existe uma conexão real no mundo, mas o personagem nunca a descobriu.
    _connect(db_session, village, arven, distance=5.0)

    _know_location(db_session, character.id, village)
    _know_location(db_session, character.id, arven)

    plan = plan_known_route(db_session, campaign.id, character.id, village.id, arven.id)

    assert plan is None


def test_plan_returns_none_when_destination_is_entirely_unknown(db_session):
    campaign = create_campaign(db_session, "Destino Desconhecido", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    hidden = Location(region_id=region.id, name="Nunca Ouvido", type="generic")
    db_session.add(hidden)
    db_session.flush()

    plan = plan_known_route(db_session, campaign.id, character.id, village.id, hidden.id)

    assert plan is None


def test_plan_never_uses_a_shortcut_the_character_does_not_know(db_session):
    """The authoritative graph has a direct, cheap shortcut; the
    character only knows the longer, discovered path — the plan must
    use what the character actually knows, never the shortest possible
    authoritative route."""
    campaign = create_campaign(db_session, "Nunca Usa Atalho Desconhecido", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    rowan = Location(region_id=region.id, name="Rowan", type="settlement", x=1, y=1)
    arven = Location(region_id=region.id, name="Arven", type="settlement", x=2, y=2)
    db_session.add_all([rowan, arven])
    db_session.flush()

    known_leg1 = _connect(db_session, village, rowan, distance=5.0)
    known_leg2 = _connect(db_session, rowan, arven, distance=5.0)
    _connect(db_session, village, arven, distance=1.0)  # atalho nunca descoberto

    for location in (village, rowan, arven):
        _know_location(db_session, character.id, location)
    discover_connection(db_session, character.id, known_leg1.id)
    discover_connection(db_session, character.id, known_leg2.id)

    plan = plan_known_route(db_session, campaign.id, character.id, village.id, arven.id)

    assert plan is not None
    assert len(plan.segments) == 2
    assert plan.total_distance == 10.0


def test_plan_for_the_same_start_and_destination_is_a_trivial_empty_plan(db_session):
    campaign = create_campaign(db_session, "Mesmo Local", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    _know_location(db_session, character.id, village)

    plan = plan_known_route(db_session, campaign.id, character.id, village.id, village.id)

    assert plan is not None
    assert plan.segments == []
    assert plan.total_distance == 0.0
