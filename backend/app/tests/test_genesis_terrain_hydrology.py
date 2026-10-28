from dataclasses import replace
import pytest
from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.hydrology.regional import build_regional_hydrology, RegionalHydrologyConfig
from app.game.world.genesis.climate.plan import build_climate_plan
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.water.plan import build_water_plan
from app.game.world.genesis.terrain.field import TerrainSampler, build_terrain_plan, checksum
from app.game.world.genesis.terrain.config import TerrainConfig
from app.game.world.genesis.terrain.hydrology import audit_regional_constraints


def test_hydro_profiles_report_conflicts_without_rewriting_sources():
    source = build_plan(42, FormationConfigV4(macro_level=2))
    h1 = build_hydrology_plan(source, HydrologyConfig(level=2))
    region = build_regional_hydrology(source, h1, 5)
    c2 = build_climate_plan(source, h1, ClimateConfigV2(level=3))
    water = build_water_plan(source, h1, c2, [region])
    sampler = TerrainSampler(build_terrain_plan(source))
    before = [checksum(p) for p in (source.to_dict(), h1.to_dict(), region, c2.to_dict(), water.to_dict())]
    report = audit_regional_constraints(sampler, h1, region, water)
    assert report["in_w1_fixed_manifest"]
    assert report["water_ledger_modified"] is False
    assert report["storage_capacity_liters"] is report["permanent_waterbody"] is None
    assert report["sample_count_upper_bound"] <= 4096
    assert [checksum(p) for p in (source.to_dict(), h1.to_dict(), region, c2.to_dict(), water.to_dict())] == before
    # Deliberately incompatible authority must report the rise, never carve a bed.
    class Raised:
        plan = sampler.plan
        def sample(self, point):
            return {"height_mm": 100_000_000}
    raised = audit_regional_constraints(Raised(), h1, region, water)
    assert raised["incompatibility_count"] == len(region["segments"]) > 0
    assert all(not r["bed_validated"] and r["conveyance_capacity"] is None for r in raised["segments"])
    with pytest.raises(ValueError, match="budget"):
        audit_regional_constraints(TerrainSampler(build_terrain_plan(source, TerrainConfig(max_hydro_samples=5))), h1, region)
    with pytest.raises(ValueError, match="mismatch"):
        audit_regional_constraints(sampler, replace(h1, source_signature="wrong"), region)


def test_progressive_inspection_does_not_extend_or_rebalance_w1(db_session):
    from app.game.world.seed import create_campaign
    from app.game.world.genesis.service import initialize_world
    from app.game.world.genesis.hydrology.service import initialize_hydrology
    from app.game.world.genesis.hydrology.regional_service import initialize_regional_hydrology, materialize_hydrology_region
    from app.game.world.genesis.climate.service import initialize_climate
    from app.game.world.genesis.water.service import initialize_water_balance
    from app.game.world.genesis.terrain.service import initialize_terrain, query_hydrology_constraints
    from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
    campaign = create_campaign(db_session, "T1 progressive constraints", world_seed=42)
    initialize_world(db_session, campaign.id, FormationConfigV4(macro_level=2))
    initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
    initialize_regional_hydrology(db_session, campaign.id)
    initialize_climate(db_session, campaign.id, ClimateConfigV2(level=3))
    water = initialize_water_balance(db_session, campaign.id)
    initialize_terrain(db_session, campaign.id)
    before = checksum(water.plan)
    with pytest.raises(ValueError, match="explicitly"):
        query_hydrology_constraints(db_session, campaign.id, 5)
    assert db_session.query(GenesisHydrologyRegion).count() == 0
    hr = materialize_hydrology_region(db_session, campaign.id, 5)
    report = query_hydrology_constraints(db_session, campaign.id, 5)
    assert not report["in_w1_fixed_manifest"]
    assert report["terrain_baseline_only"]
    assert checksum(water.plan) == before and water.manifest == []
    hr.changes = {"events": [{"kind": "future_event"}]}
    with pytest.raises(ValueError, match="event-aware"):
        query_hydrology_constraints(db_session, campaign.id, 5)
