"""Phase 16B — Regional Boundary Foundation."""

from app.db.models.location import Location, LocationConnection
from app.db.models.subregion import Subregion
from app.game.travel.service import find_connection
from app.game.world.boundaries import create_regional_boundary, get_regional_boundaries
from app.game.world.seed import create_campaign, seed_initial_region


def test_create_regional_boundary_materializes_a_reachable_frontier(db_session):
    campaign = create_campaign(db_session, "Fronteira", world_seed=7)
    region, _village = seed_initial_region(db_session, campaign.id)

    boundary = create_regional_boundary(db_session, campaign.id, region.id)

    assert boundary.source_region_id == region.id
    assert boundary.destination_region_id is None
    assert boundary.name != ""
    assert boundary.boundary_side != ""

    frontier = db_session.get(Location, boundary.frontier_location_id)
    assert frontier is not None
    assert frontier.region_id == region.id
    assert frontier.type == "region_frontier"
    assert frontier.materialization_tier == 1

    subregion = db_session.get(Subregion, boundary.anchor_subregion_id)
    assert subregion is not None
    assert subregion.region_id == region.id

    # The frontier must be reachable via the ordinary travel graph, not a
    # special-cased destination.
    inbound = (
        db_session.query(LocationConnection)
        .filter(LocationConnection.to_location_id == frontier.id)
        .all()
    )
    assert len(inbound) == 1
    outbound = find_connection(db_session, frontier.id, inbound[0].from_location_id)
    assert outbound is not None


def test_boundary_anchors_to_the_outermost_subregion_by_default(db_session):
    campaign = create_campaign(db_session, "Fronteira Distante", world_seed=11)
    region, _village = seed_initial_region(db_session, campaign.id)

    outermost = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == region.id)
        .order_by(Subregion.order_index.desc())
        .first()
    )

    boundary = create_regional_boundary(db_session, campaign.id, region.id)

    assert boundary.anchor_subregion_id == outermost.id


def test_boundary_name_matches_anchor_subregion_biome_flavor(db_session):
    from app.game.world.content_pools import BOUNDARY_NAME_POOL_BY_BIOME

    campaign = create_campaign(db_session, "Fronteira Bioma", world_seed=23)
    region, _village = seed_initial_region(db_session, campaign.id)

    boundary = create_regional_boundary(db_session, campaign.id, region.id)
    subregion = db_session.get(Subregion, boundary.anchor_subregion_id)

    pool = BOUNDARY_NAME_POOL_BY_BIOME.get(str(subregion.biome), BOUNDARY_NAME_POOL_BY_BIOME["FRONTIER"])
    assert (boundary.name, boundary.description) in pool


def test_multiple_boundaries_on_distinct_subregions_are_both_listed(db_session):
    campaign = create_campaign(db_session, "Duas Fronteiras", world_seed=31)
    region, _village = seed_initial_region(db_session, campaign.id)

    subregions = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == region.id)
        .order_by(Subregion.order_index.desc())
        .limit(2)
        .all()
    )
    assert len(subregions) == 2

    first = create_regional_boundary(db_session, campaign.id, region.id, anchor_subregion_id=subregions[0].id)
    second = create_regional_boundary(db_session, campaign.id, region.id, anchor_subregion_id=subregions[1].id)

    boundaries = get_regional_boundaries(db_session, campaign.id, region.id)
    assert {b.id for b in boundaries} == {first.id, second.id}


def test_boundary_generation_is_deterministic_per_seed(db_session):
    campaign_a = create_campaign(db_session, "Determinismo A", world_seed=99)
    region_a, _village_a = seed_initial_region(db_session, campaign_a.id)
    boundary_a = create_regional_boundary(db_session, campaign_a.id, region_a.id)

    campaign_b = create_campaign(db_session, "Determinismo B", world_seed=99)
    region_b, _village_b = seed_initial_region(db_session, campaign_b.id)
    boundary_b = create_regional_boundary(db_session, campaign_b.id, region_b.id)

    assert boundary_a.name == boundary_b.name
    assert boundary_a.boundary_side == boundary_b.boundary_side
    assert boundary_a.generation_seed == boundary_b.generation_seed
