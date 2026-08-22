"""Phase 16R — Region Validation (cross-Region checks)."""

import pytest

from app.db.models.location import Location
from app.db.models.subregion import Subregion
from app.game.world.boundaries import create_regional_boundary
from app.game.world.cross_region_routes import connect_boundary_to_neighbor_region
from app.game.world.neighbor_region import materialize_neighbor_region
from app.game.world.seed import create_campaign, seed_initial_region
from app.game.world.validation import RegionValidationError, validate_neighbor_region_package


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Validacao {world_seed}", world_seed=world_seed)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)
    connect_boundary_to_neighbor_region(db_session, boundary, neighbor)
    return campaign, source_region, boundary, neighbor


def test_a_correctly_materialized_neighbor_passes_validation(db_session):
    _campaign, _source, boundary, neighbor = _setup(db_session, 500)

    validate_neighbor_region_package(db_session, boundary, neighbor)


def test_validation_rejects_a_boundary_pointing_at_the_wrong_region(db_session):
    _campaign, _source, boundary, neighbor = _setup(db_session, 501)
    boundary.destination_region_id = "region_not_this_one"

    with pytest.raises(RegionValidationError):
        validate_neighbor_region_package(db_session, boundary, neighbor)


def test_validation_rejects_geography_discontinuity(db_session):
    _campaign, _source, boundary, neighbor = _setup(db_session, 502)
    neighbor_first_subregion = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == neighbor.id, Subregion.order_index == 0)
        .one()
    )
    neighbor_first_subregion.biome = "SOME_INCOMPATIBLE_BIOME_FOR_TEST"

    with pytest.raises(RegionValidationError):
        validate_neighbor_region_package(db_session, boundary, neighbor)


def test_validation_rejects_a_route_pointing_outside_the_neighbor_region(db_session):
    from app.game.world.boundaries import get_boundary_routes

    _campaign, source_region, boundary, neighbor = _setup(db_session, 503)
    route = get_boundary_routes(db_session, boundary.id)[0]
    route.destination_location_id = boundary.frontier_location_id  # a location in the SOURCE region

    with pytest.raises(RegionValidationError):
        validate_neighbor_region_package(db_session, boundary, neighbor)


def test_validation_rejects_duplicate_location_names_across_regions(db_session):
    _campaign, source_region, boundary, neighbor = _setup(db_session, 504)

    some_source_location = (
        db_session.query(Location).filter(Location.region_id == source_region.id).first()
    )
    colliding_location = (
        db_session.query(Location).filter(Location.region_id == neighbor.id).first()
    )
    colliding_location.name = some_source_location.name
    db_session.flush()

    with pytest.raises(RegionValidationError):
        validate_neighbor_region_package(db_session, boundary, neighbor)
