from dataclasses import replace
import hashlib
import json
import os
import subprocess
import sys
import tracemalloc

import pytest

from app.game.world.genesis.water.balance import solve, WaterSolution, freeze_period, validate, STORES
from app.game.world.genesis.water.config import WaterConfig
from app.game.world.genesis.water.plan import build_water_plan, compile_evidence, load_water_plan
from app.game.world.genesis.water.query import node_record, regional_sector_record, boundary_record, regime
from app.game.world.genesis.formation_plan import build_plan, indexed_cell
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.hydrology.regional import build_regional_hydrology, RegionalHydrologyConfig
from app.game.world.genesis.climate.plan import build_climate_plan, _solve_climate
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.geometry import geometry as climate_geometry
from app.game.world.genesis.sphere_topology import CellKey, SurfacePoint, cell_at


def bucket(p, *, pet=None, snow=None, temperatures=None, parent=(1, -1), marine=(False, True),
           areas=None, capacity=None, open_routes=None, distances=None, config=None):
    count = len(parent)
    zero = [[0]*count for _ in range(4)]
    return solve(areas or (1,)*count, marine, parent, tuple(reversed(range(count))), p,
        pet or zero, snow or zero, temperatures or [[2000]*count for _ in range(4)], capacity or (0,)*count,
        (True,)*count if open_routes is None else open_routes, distances or (0,)*count, 360,
        config or WaterConfig(warmup_years=0, soil_capacity_mm=0, surface_capacity_mm=0,
                             infiltration_mm_per_day=0, reservoir_wetted_area_ppm=0))


def test_confluence_combines_once_and_ocean_is_sink_only():
    p = [[100, 50, 0, 99999] for _ in range(4)]
    result = bucket(p, parent=(2, 2, 3, -1), marine=(False, False, False, True))
    for period in result.periods:
        assert period["fluxes"]["outflow"] == (100, 50, 150, 0)
        assert period["fluxes"]["incoming"] == (0, 0, 150, 150)
        assert period["totals"]["precipitation"] == period["totals"]["ocean_export"] == 150
        assert period["totals"]["residual_liters"] == 0


def test_actual_et_never_exceeds_available_water_or_pet():
    result = bucket([[100, 0]]*4, pet=[[1000, 0]]*4)
    assert all(p["totals"]["evapotranspiration"] == 100 and not p["totals"]["outflow"] for p in result.periods)


def test_infiltration_soil_retention_and_delayed_et_are_internal_transfers():
    config = WaterConfig(warmup_years=0, soil_capacity_mm=100, surface_capacity_mm=0, soil_release_ppm_per_day=0)
    result = bucket([[100, 0], [0, 0], [0, 0], [0, 0]], pet=[[0, 0], [50, 0], [0, 0], [0, 0]], config=config)
    assert result.periods[0]["stores"]["soil"][0] == 100
    assert result.periods[1]["stores"]["soil"][0] == 50
    assert result.periods[1]["fluxes"]["evapotranspiration"][0] == 50
    assert all(p["totals"]["ocean_export"] == 0 for p in result.periods)


def test_snow_accumulates_then_melts_without_new_water():
    p = [[100, 0], [0, 0], [0, 0], [0, 0]]
    result = bucket(p, snow=p, temperatures=[[-1000, 0], [1000, 0], [0, 0], [0, 0]])
    assert result.periods[0]["stores"]["snow"][0] == 100
    assert result.periods[1]["fluxes"]["melt"][0] == 100
    assert result.periods[1]["totals"]["ocean_export"] == 100
    assert sum(p["totals"]["ocean_export"] for p in result.periods) == 100


def test_storage_overflow_and_seasonal_drying_with_declared_capacity():
    config = WaterConfig(warmup_years=0, soil_capacity_mm=0, surface_capacity_mm=0, reservoir_wetted_area_ppm=1000000)
    result = bucket([[30, 0], [30, 0], [0, 0], [0, 0]], capacity=(50, 0),
                    pet=[[0, 0], [0, 0], [20, 0], [1000, 0]], config=config)
    assert [p["stores"]["depression"][0] for p in result.periods] == [30, 50, 30, 0]
    assert result.periods[1]["fluxes"]["outflow"][0] == 10
    assert result.periods[2]["fluxes"]["evapotranspiration"][0] == 20


def test_blocked_water_is_carried_across_periods_and_years():
    config = WaterConfig(warmup_years=2, soil_capacity_mm=0, surface_capacity_mm=0, reservoir_wetted_area_ppm=0)
    result = bucket([[100, 0]]*4, open_routes=(False, False), config=config)
    assert result.initial_stores[STORES.index("unresolved")][0] == 800
    assert result.periods[-1]["stores"]["unresolved"][0] == 1200
    assert all(p["totals"]["outflow"] == 0 for p in result.periods)
    closed = bucket([[100]]*4, parent=(-1,), marine=(False,), capacity=(25,), open_routes=(False,))
    assert closed.periods[-1]["stores"]["depression"][0] == 25
    assert closed.periods[-1]["stores"]["unresolved"][0] == 375


def test_transport_lag_retains_rounding_and_classifies_only_model_window():
    result = bucket([[100, 0]]*4, distances=(7776000, 0))  # 1m/s * 90 days, release fraction 1/2
    assert result.periods[0]["fluxes"]["outflow"][0] == 50
    assert result.periods[1]["fluxes"]["outflow"][0] == 75
    assert result.periods[-1]["stores"]["channel"][0] > 0
    assert regime([0, 0, 0, 0], 360, 0) == "potentially_dry"
    assert regime([1, 0, 0, 0], 360, 0) == "temporary"
    assert regime([1, 0, 2, 0], 360, 0) == "seasonal"
    assert regime([1, 2, 3, 4], 360, 0) == "regularly_supplied_in_model_window"


@pytest.mark.parametrize("data", [{"water_version": 2}, {"water_version": True}, {"warmup_years": 8},
    {"soil_capacity_mm": -1}, {"source_climate_version": True}, {"channel_velocity_mm_s": 0}])
def test_w1_config_budgets_are_strict(data):
    with pytest.raises(ValueError):
        WaterConfig(**data)


@pytest.fixture(scope="module")
def sources():
    s = build_plan(42, FormationConfigV4(macro_level=2))
    h = build_hydrology_plan(s, HydrologyConfig(level=2))
    c = build_climate_plan(s, h, ClimateConfigV2(level=3))
    return s, h, c


@pytest.fixture(scope="module")
def water(sources):
    return build_water_plan(*sources)


def test_sources_unchanged_real_climate_water_budget_and_roundtrip(sources, water, monkeypatch):
    before = json.dumps([p.to_dict() for p in sources], sort_keys=True)
    def forbidden(*args, **kwargs):
        raise AssertionError("W1 load must not regenerate upstream layers or rerun balance")
    monkeypatch.setattr("app.game.world.genesis.water.plan.solve", forbidden)
    loaded = load_water_plan(json.loads(json.dumps(water.to_dict())), sources[1], sources[2], water.hr_signature)
    assert loaded == water
    assert all(p["totals"]["residual_liters"] == 0 for p in water.solution.periods)
    assert all(p["totals"]["outflow"] == 0 for p in water.solution.periods)  # no region proof implicitly invented
    assert any(p["totals"]["local_runoff"] > 0 for p in water.solution.periods)
    assert json.dumps([p.to_dict() for p in sources], sort_keys=True) == before
    record = node_record(water, 5)
    assert record["macro_area_m2"] == sources[1].cell_area_m2[5]
    assert record["lake_permanent"] is record["perennial"] is None
    with pytest.raises(TypeError):
        water.solution.periods[0]["fluxes"]["outflow"] = ()


def flat_fixture(sources):
    """Controlled forcing/topology fixture, never used in production save creation."""
    s, original, _ = sources
    h = replace(original, heights=(0,)*len(original.heights), drainage=replace(original.drainage, head=(0,)*len(original.heights)))
    cfg = ClimateConfigV2(level=3, radiative_offset_centi_c=2000, insolation_gain_centi_c=0,
                          lapse_centi_c_per_km=0, pet_scale_milli_mm_per_day=0)
    count = len(climate_geometry(3).points)
    c = _solve_climate(s.signature, h.signature, h.radius_m, h.sea_level_m, (-100,)*count, (True,)*count, 12000000, cfg)
    return s, h, c


def test_fixed_hr_evidence_enables_real_model_transfers_and_order_independence(sources):
    s, h, c = flat_fixture(sources)
    node = next(n for n in h.channel_index if sum(h.drainage.parent[i] == n for i in h.channel_index) >= 2)
    nodes = sorted({node, h.drainage.parent[node]} | {i for i in h.channel_index if h.drainage.parent[i] == node})
    regions = [build_regional_hydrology(s, h, n, _sampler=lambda p: 0) for n in nodes]
    config = WaterConfig(warmup_years=0, soil_capacity_mm=0, surface_capacity_mm=0, flow_presence_liters_per_second=0)
    a, b = build_water_plan(s, h, c, regions, config=config), build_water_plan(s, h, c, list(reversed(regions)), config=config)
    assert a == b
    assert node_record(a, node)["model_fed_sampled_corridor"]
    for period in a.solution.periods:
        assert period["fluxes"]["incoming"][node] == sum(period["fluxes"]["outflow"][i] for i in nodes if h.drainage.parent[i] == node)
    assert all(boundary_record(a, n)["period_transfer_liters"] == boundary_record(b, n)["period_transfer_liters"] for n in nodes if h.drainage.parent[n] >= 0)


@pytest.mark.parametrize("level", [5, 13, 24])
def test_shared_water_flux_between_faces_and_local_sectors(sources, level):
    s, h, c = flat_fixture(sources)
    g = geometry(h.config.level)
    source = next(i for i in h.channel_index if indexed_cell(i, h.config.level).face != indexed_cell(h.drainage.parent[i], h.config.level).face)
    target = h.drainage.parent[source]
    regions = [build_regional_hydrology(s, h, n, _sampler=lambda p: 0) for n in (source, target)]
    plan = build_water_plan(s, h, c, regions, config=WaterConfig(soil_capacity_mm=0, surface_capacity_mm=0))
    port = next(p for p in regions[0]["ports"] if p["source_node"] == source)
    ray = SurfacePoint(*port["point"])
    boundaries = []
    for node, region in zip((source, target), regions):
        near = SurfacePoint(*(a+(2**28-1)*b for a, b in zip(g.points[node].xyz, ray.xyz)))
        snapshot = regional_sector_record(plan, cell_at(near, level), region)
        boundaries.append(next(b for b in snapshot["boundaries"] if b["source_node"] == source))
        assert any(piece["model_fed_sampled_segment"] for piece in snapshot["segments"])
    assert boundaries[0] == boundaries[1]
    assert any(boundaries[0]["period_transfer_liters"])


def test_orange_hr_storage_or_incompatible_routes_never_transport(sources):
    s, h, c = sources
    regions = [build_regional_hydrology(s, h, n) for n in (5, h.drainage.parent[5])]
    plan = build_water_plan(s, h, c, regions)
    assert plan.support[5] != "bilateral_downhill_validated"
    assert all(p["fluxes"]["outflow"][5] == 0 for p in plan.solution.periods)
    assert all(p["totals"]["residual_liters"] == 0 for p in plan.solution.periods)


def test_known_ocean_boundary_stage_does_not_require_filling_an_infinite_ocean(sources):
    s, h, c = flat_fixture(sources)
    source = next(i for i in h.channel_index if h.drainage.marine[h.drainage.parent[i]])
    target = h.drainage.parent[source]
    heights = list(h.heights)
    heights[target] = -1
    h = replace(h, heights=tuple(heights))
    ray = geometry(h.config.level).points[target]
    regions = [build_regional_hydrology(s, h, i, _sampler=lambda p: -1 if p == ray else 0) for i in (source, target)]
    plan = build_water_plan(s, h, c, regions, config=WaterConfig(soil_capacity_mm=0, surface_capacity_mm=0))
    assert plan.support[source] == "bilateral_downhill_validated"
    assert any(p["fluxes"]["ocean_export"][target] > 0 for p in plan.solution.periods)
    assert all(p["fluxes"]["precipitation"][target] == 0 for p in plan.solution.periods)


def test_c1_legacy_is_explicit_and_w1_never_converts_it(sources):
    s, h, _ = sources
    c1 = build_climate_plan(s, h, ClimateConfig(level=3))
    with pytest.raises(ValueError):
        build_water_plan(s, h, c1)
    assert build_water_plan(s, h, c1, config=WaterConfig(source_climate_version=1)).config.source_climate_version == 1


def test_ledger_corruption_cycles_and_invalid_evidence_fail_closed(sources, water):
    data = json.loads(json.dumps(water.to_dict()))
    data["solution"]["periods"][0]["fluxes"]["incoming"][5] += 1
    with pytest.raises(ValueError):
        load_water_plan(data, sources[1], sources[2], water.hr_signature)
    with pytest.raises(ValueError):
        bucket([[100]]*4, parent=(0,), marine=(False,))
    with pytest.raises(ValueError):
        compile_evidence(sources[1], RegionalHydrologyConfig(), [{}]*33)


def test_process_replay_of_w1(water):
    code = ("import json,hashlib; from app.game.world.genesis.formation_plan import build_plan; "
        "from app.game.world.genesis.formation_v4 import FormationConfigV4; "
        "from app.game.world.genesis.hydrology.config import HydrologyConfig; "
        "from app.game.world.genesis.hydrology.plan import build_hydrology_plan; "
        "from app.game.world.genesis.climate.v2 import ClimateConfigV2; "
        "from app.game.world.genesis.climate.plan import build_climate_plan; "
        "from app.game.world.genesis.water.plan import build_water_plan; "
        "s=build_plan(42,FormationConfigV4(macro_level=2)); h=build_hydrology_plan(s,HydrologyConfig(level=2)); "
        "c=build_climate_plan(s,h,ClimateConfigV2(level=3)); w=build_water_plan(s,h,c); "
        "print(hashlib.sha256(json.dumps(w.to_dict(),sort_keys=True).encode()).hexdigest())")
    expected = hashlib.sha256(json.dumps(water.to_dict(), sort_keys=True).encode()).hexdigest()
    assert expected == "46d7c758b3bb3a3948bcf24c40b8270f57e4480543c3bedb70244fc3a70da027"
    for seed in ("1", "999"):
        assert subprocess.check_output([sys.executable, "-c", code], text=True, env={**os.environ, "PYTHONHASHSEED": seed}).strip() == expected


def test_water_metrics_basin_conservation_and_offline_images(water, tmp_path):
    from PIL import Image
    from app.game.world.genesis.water.preview import metrics, write_preview
    data = metrics(water)
    assert all(row["residual_liters"] == 0 for row in data["catchment_budgets"])
    assert sum(row["precipitation_liters"] for row in data["catchment_budgets"]) == data["year_totals_liters"]["precipitation"]
    write_preview(water, tmp_path, 42)
    with Image.open(tmp_path/"water.png") as image:
        assert image.size == (1920, 1192)


@pytest.mark.parametrize("seed,radius", [(0, 6371000), (42, 63710000), (2026, 637100000), (42, 10**12)])
def test_multi_seed_giant_worlds_memory_and_mass(seed, radius):
    s = build_plan(seed, FormationConfigV4(radius_m=radius, macro_level=2))
    h = build_hydrology_plan(s, HydrologyConfig(level=2))
    c = build_climate_plan(s, h, ClimateConfigV2(level=3))
    tracemalloc.start()
    try:
        water = build_water_plan(s, h, c)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 64*1024*1024
    assert all(p["totals"]["residual_liters"] == 0 for p in water.solution.periods)
