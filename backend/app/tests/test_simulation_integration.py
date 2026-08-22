"""Phase 16T — Simulation Integration."""

import random

from app.core.enums import RegionMaterializationRequestSource
from app.db.models.location import Location
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.players.service import simulated_player_arrival_locations
from app.game.world.boundaries import create_regional_boundary
from app.game.world.materialization_orchestrator import fulfill_region_materialization_request
from app.game.world.neighbor_region import materialize_neighbor_region
from app.game.world.region_materialization import request_region_materialization
from app.game.world.seed import create_campaign, seed_initial_region
from app.game.world.simulation_integration import enable_simulated_player_arrivals_for_region


def test_enabling_arrivals_covers_every_settlement_in_the_region(db_session):
    campaign = create_campaign(db_session, "Simulacao Direta", world_seed=700)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)

    settlement_location_ids = {
        row[0]
        for row in db_session.query(Settlement.location_id)
        .join(Location, Location.id == Settlement.location_id)
        .join(Subregion, Subregion.id == Location.subregion_id)
        .filter(Subregion.region_id == neighbor.id)
        .all()
    }
    assert settlement_location_ids

    enabled = enable_simulated_player_arrivals_for_region(db_session, campaign.id, neighbor.id)

    assert set(enabled) == settlement_location_ids


def test_fulfilling_a_request_makes_the_neighbor_arrival_eligible(db_session):
    campaign = create_campaign(db_session, "Simulacao Fulfillment", world_seed=701)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
    request = request_region_materialization(
        db_session, campaign.id, source_region.id, RegionMaterializationRequestSource.SIMULATED_CHARACTER,
    )

    before = {loc.id for loc in simulated_player_arrival_locations(db_session, campaign.id)}

    neighbor = fulfill_region_materialization_request(db_session, request.id, boundary, region_index=1)

    after_locations = simulated_player_arrival_locations(db_session, campaign.id)
    after = {loc.id for loc in after_locations}

    neighbor_location_ids = {
        row[0]
        for row in db_session.query(Location.id).filter(Location.region_id == neighbor.id).all()
    }

    newly_enabled = after - before
    assert newly_enabled
    assert newly_enabled <= neighbor_location_ids


def test_neighbor_settlements_can_actually_be_selected_for_new_arrivals(db_session):
    from app.game.players.service import select_simulated_player_arrival_location

    campaign = create_campaign(db_session, "Simulacao Selecao", world_seed=702)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
    request = request_region_materialization(
        db_session, campaign.id, source_region.id, RegionMaterializationRequestSource.ECONOMY,
    )
    neighbor = fulfill_region_materialization_request(db_session, request.id, boundary, region_index=1)

    neighbor_location_ids = {
        row[0]
        for row in db_session.query(Location.id).filter(Location.region_id == neighbor.id).all()
    }

    rng = random.Random(1)
    picked_in_neighbor = False
    for _ in range(200):
        location = select_simulated_player_arrival_location(db_session, campaign.id, rng=rng)
        if location is not None and location.id in neighbor_location_ids:
            picked_in_neighbor = True
            break

    assert picked_in_neighbor
