"""Phase 16I/16J/16K/16L/16M/16N/16O — materializing a neighboring
Region."""

from app.core.enums import DiscoveryStatus
from app.db.models.regional_threat import RegionalThreat
from app.db.models.settlement import Settlement
from app.db.models.subregion import Subregion
from app.game.world.boundaries import create_regional_boundary
from app.game.world.generation import derive_seed
from app.game.world.generator import MAX_SUBREGIONS, MIN_SUBREGIONS
from app.game.world.neighbor_region import materialize_neighbor_region
from app.game.world.seed import create_campaign, seed_initial_region


def test_materialize_neighbor_region_produces_a_full_massive_region(db_session):
    campaign = create_campaign(db_session, "Vizinha Completa", world_seed=200)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)

    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)

    assert neighbor.id != source_region.id
    assert neighbor.name != source_region.name
    assert neighbor.skeleton_complete is True

    subregions = db_session.query(Subregion).filter(Subregion.region_id == neighbor.id).all()
    assert MIN_SUBREGIONS <= len(subregions) <= MAX_SUBREGIONS

    # Settlement has no region_id of its own, so scope through the
    # subregion set instead.
    subregion_ids = {s.id for s in subregions}
    from app.db.models.location import Location

    neighbor_settlement_location_ids = {
        row[0]
        for row in db_session.query(Location.id)
        .filter(Location.region_id == neighbor.id, Location.subregion_id.in_(subregion_ids))
        .all()
    }
    settlements_in_neighbor = [s for s in db_session.query(Settlement).all() if s.location_id in neighbor_settlement_location_ids]
    assert len(settlements_in_neighbor) >= 1

    threats = db_session.query(RegionalThreat).filter(RegionalThreat.subregion_id.in_(subregion_ids)).all()
    assert len(threats) == len(subregions)


def test_neighbor_region_starts_rumored_not_discovered(db_session):
    campaign = create_campaign(db_session, "Vizinha Rumor", world_seed=201)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)

    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)

    assert neighbor.discovery_status == DiscoveryStatus.RUMORED.value


def test_neighbor_first_subregion_biome_continues_the_boundary_terrain(db_session):
    campaign = create_campaign(db_session, "Vizinha Continuidade", world_seed=202)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
    anchor_subregion = db_session.get(Subregion, boundary.anchor_subregion_id)

    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)

    neighbor_first_subregion = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == neighbor.id, Subregion.order_index == 0)
        .one()
    )
    assert neighbor_first_subregion.biome == anchor_subregion.biome


def test_neighbor_region_seed_is_derived_from_region_index_not_reused(db_session):
    campaign = create_campaign(db_session, "Vizinha Seed", world_seed=203)
    source_region, _village = seed_initial_region(db_session, campaign.id)
    boundary = create_regional_boundary(db_session, campaign.id, source_region.id)

    neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)

    assert neighbor.generation_seed == derive_seed(campaign.world_seed, "region:1")
    assert neighbor.generation_seed != source_region.generation_seed


def test_materialize_neighbor_region_is_deterministic_per_seed(db_session):
    campaign_a = create_campaign(db_session, "Vizinha Determinismo A", world_seed=204)
    source_a, _village_a = seed_initial_region(db_session, campaign_a.id)
    boundary_a = create_regional_boundary(db_session, campaign_a.id, source_a.id)
    neighbor_a = materialize_neighbor_region(db_session, campaign_a.id, boundary_a, region_index=1)

    campaign_b = create_campaign(db_session, "Vizinha Determinismo B", world_seed=204)
    source_b, _village_b = seed_initial_region(db_session, campaign_b.id)
    boundary_b = create_regional_boundary(db_session, campaign_b.id, source_b.id)
    neighbor_b = materialize_neighbor_region(db_session, campaign_b.id, boundary_b, region_index=1)

    assert neighbor_a.name == neighbor_b.name
    assert neighbor_a.generation_seed == neighbor_b.generation_seed

    subregions_a = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == neighbor_a.id)
        .order_by(Subregion.order_index)
        .all()
    )
    subregions_b = (
        db_session.query(Subregion)
        .filter(Subregion.region_id == neighbor_b.id)
        .order_by(Subregion.order_index)
        .all()
    )
    assert [s.name for s in subregions_a] == [s.name for s in subregions_b]
    assert [s.biome for s in subregions_a] == [s.biome for s in subregions_b]


def test_historical_summary_includes_political_tension_when_documented(db_session):
    from app.game.world.boundaries import get_boundary_barriers
    from app.core.enums import BoundaryBarrierCategory

    found_case = False
    for seed in range(30):
        campaign = create_campaign(db_session, f"Vizinha Tensao {seed}", world_seed=seed)
        source_region, _village = seed_initial_region(db_session, campaign.id)
        boundary = create_regional_boundary(db_session, campaign.id, source_region.id)
        barriers = get_boundary_barriers(db_session, boundary.id)
        has_political = any(b.category == BoundaryBarrierCategory.POLITICAL.value for b in barriers)
        if not has_political:
            continue
        found_case = True

        neighbor = materialize_neighbor_region(db_session, campaign.id, boundary, region_index=1)
        assert "Tensão política" in neighbor.historical_summary

    assert found_case
