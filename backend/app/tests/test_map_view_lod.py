"""Phase 20O — Large-World Rendering / Level of Detail."""

from app.core.enums import DiscoveryStatus
from app.db.models.location import Location, LocationConnection
from app.game.character.service import create_character
from app.game.discovery.service import discover_connection, set_location_discovery
from app.game.map.annotations import create_annotation
from app.game.map.view import get_map_view
from app.game.world.seed import create_campaign, seed_initial_region


def test_far_detail_level_keeps_only_tier_one_locations(db_session):
    campaign = create_campaign(db_session, "LOD Longe So Tier Um", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    stub = Location(region_id=region.id, name="Vilarejo Menor", type="settlement", materialization_tier=2)
    db_session.add(stub)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, stub.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, detail_level="far")

    location_ids = {item.id for item in view.locations}
    assert village.id in location_ids
    assert stub.id not in location_ids


def test_default_detail_level_shows_every_tier(db_session):
    campaign = create_campaign(db_session, "LOD Padrao Mostra Tudo", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    stub = Location(region_id=region.id, name="Vilarejo Menor", type="settlement", materialization_tier=2)
    db_session.add(stub)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, stub.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id)

    location_ids = {item.id for item in view.locations}
    assert stub.id in location_ids


def test_viewport_filters_out_positioned_locations_outside_bounds(db_session):
    campaign = create_campaign(db_session, "LOD Viewport Filtra Fora", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    far_away = Location(region_id=region.id, name="Bem Longe", type="settlement", x=9999, y=9999)
    db_session.add(far_away)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, far_away.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, viewport=(-10.0, -10.0, 10.0, 10.0))

    location_ids = {item.id for item in view.locations}
    assert village.id in location_ids
    assert far_away.id not in location_ids


def test_viewport_never_excludes_a_location_with_no_exact_position(db_session):
    from app.core.enums import GeographicKnowledgeAspect, GeographicPrecision, KnowerType
    from app.game.knowledge.geography import ensure_geographic_fact, geographic_fact_key, grant_fact_with_precision

    campaign = create_campaign(db_session, "LOD Viewport Preserva Incertos", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    distant = Location(region_id=region.id, name="Arven", type="settlement", x=9999, y=9999)
    db_session.add(distant)
    db_session.flush()
    ensure_geographic_fact(
        db_session, campaign.id, "location", distant.id,
        GeographicKnowledgeAspect.EXISTENCE, "Um povoado existe.",
    )
    grant_fact_with_precision(
        db_session, campaign.id,
        geographic_fact_key("location", distant.id, GeographicKnowledgeAspect.EXISTENCE),
        KnowerType.PLAYER, character.id, precision=GeographicPrecision.VAGUE,
    )
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)

    view = get_map_view(db_session, campaign.id, character.id, viewport=(-10.0, -10.0, 10.0, 10.0))

    location_ids = {item.id for item in view.locations}
    assert distant.id in location_ids


def test_a_route_to_a_lod_filtered_location_disappears_with_it(db_session):
    campaign = create_campaign(db_session, "LOD Rota Some Junto", world_seed=5)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    far_away = Location(region_id=region.id, name="Bem Longe", type="settlement", x=9999, y=9999)
    db_session.add(far_away)
    db_session.flush()
    connection = LocationConnection(from_location_id=village.id, to_location_id=far_away.id, distance=1.0)
    db_session.add(connection)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, far_away.id, DiscoveryStatus.VISITED)
    discover_connection(db_session, character.id, connection.id)

    view = get_map_view(db_session, campaign.id, character.id, viewport=(-10.0, -10.0, 10.0, 10.0))

    assert view.routes == []


def test_an_annotation_on_a_lod_filtered_location_disappears_with_it(db_session):
    campaign = create_campaign(db_session, "LOD Anotacao Some Junto", world_seed=6)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    far_away = Location(region_id=region.id, name="Bem Longe", type="settlement", x=9999, y=9999)
    db_session.add(far_away)
    db_session.flush()
    set_location_discovery(db_session, character.id, village.id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, far_away.id, DiscoveryStatus.VISITED)
    create_annotation(db_session, campaign.id, character.id, far_away.id, "Nota qualquer.")

    view = get_map_view(db_session, campaign.id, character.id, viewport=(-10.0, -10.0, 10.0, 10.0))

    assert view.annotations == []
