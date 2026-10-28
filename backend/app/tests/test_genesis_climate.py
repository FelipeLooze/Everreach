from dataclasses import replace
import hashlib
import json
import os
import subprocess
import sys
import tracemalloc

import pytest

from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.geometry import Q, geometry, interpolate, stencil, unit
from app.game.world.genesis.climate.physics import (
    condensation, declinations, lapse, seasonal_temperature, solar_forcing, transport, wind,
)
from app.game.world.genesis.climate.plan import _solve_climate, build_climate_plan, load_climate_plan
from app.game.world.genesis.climate.query import hydrology_inputs, sample_climate, sample_regional_climate, season_at_phase
from app.game.world.genesis.sphere_topology import BASES, SurfacePoint, face_point


@pytest.fixture(scope="module")
def sources():
    s = build_plan(42, FormationConfigV4(macro_level=2))
    h = build_hydrology_plan(s, HydrologyConfig(level=2))
    return s, h


@pytest.fixture(scope="module")
def climate(sources):
    return build_climate_plan(*sources, ClimateConfig(level=3))


@pytest.mark.parametrize("values", [{"climate_version": 2}, {"climate_version": True}, {"level": 6}, {"level": True},
    {"axial_tilt_mdeg": -1}, {"transport_iterations": 65}, {"maritime_length_m": 0},
    {"hadley_edge_mdeg": 50_000, "polar_edge_mdeg": 50_000}, {"weather": True}])
def test_c1_configuration_is_explicit_and_bounded(values):
    with pytest.raises(ValueError):
        ClimateConfig(**values)


@pytest.mark.parametrize("level", [3, 4, 5])
def test_cube_vertex_budget_and_shared_chart_interpolation(level):
    g, n = geometry(level), 2**level
    assert len(g.points) == 6*4**level+2 <= 6146
    assert all(len(adjacent) in (3, 4) for adjacent in g.adjacent)
    values = tuple((i*2341)%100_000 for i in range(len(g.points)))
    for face in range(6):
        for x, y in ((0, n//3), (n, n//3), (n//3, 0), (n//3, n), (0, 0), (n, n)):
            point = face_point(face, x, y, n)
            faces = [i for i, (normal, _, _) in enumerate(BASES)
                     if sum(a*b for a, b in zip(point.xyz, normal)) == max(map(abs, point.xyz))]
            results = [interpolate(values, stencil(point, level, f)) for f in faces]
            assert len(set(results)) == 1
    assert geometry.cache_info().maxsize == 2


def test_solar_latitude_hemisphere_seasons_maritime_damping_and_lapse():
    config = ClimateConfig(level=3)
    equator = unit(SurfacePoint(1, 0, 0))
    north, south = unit(SurfacePoint(1, 0, 1)), unit(SurfacePoint(1, 0, -1))
    te, _ = seasonal_temperature(equator, 0, config)
    tn, _ = seasonal_temperature(north, 0, config)
    ts, _ = seasonal_temperature(south, 0, config)
    ocean, _ = seasonal_temperature(north, Q, config)
    polar, _ = seasonal_temperature(unit(SurfacePoint(0, 0, 1)), 0, config)
    assert sum(te) > sum(tn) > sum(polar)
    assert tn[1] > tn[3] and ts[3] > ts[1]
    assert abs(tn[1]-ts[3]) <= 2 and abs(tn[3]-ts[1]) <= 2
    assert max(te)-min(te) < max(tn)-min(tn)
    assert max(ocean)-min(ocean) < max(tn)-min(tn)
    assert lapse(2000, 1000, config) == 1400
    assert lapse(2000, -4000, config) == 2000
    zero_tilt = config.model_copy(update={"axial_tilt_mdeg": 0})
    assert len(set(seasonal_temperature(north, 0, zero_tilt)[0])) == 1
    d = declinations(config)
    assert solar_forcing(unit(SurfacePoint(0, 0, 1)), d[3]) == 0
    assert solar_forcing(unit(SurfacePoint(0, 0, 1)), d[1]) > 0


def test_winds_have_expected_bands_are_tangent_and_well_defined_at_poles():
    config = ClimateConfig()
    tropical = wind(unit(SurfacePoint(1, 0, 0)), 0, config)
    middle = wind(unit(SurfacePoint(1, 0, 1)), 0, config)
    assert tropical[1] < 0 < middle[1]
    for point in (SurfacePoint(1, 2, 3), SurfacePoint(-1, -4, 2), SurfacePoint(0, 0, 1), SurfacePoint(0, 0, -1)):
        direction = unit(point)
        vector = wind(direction, 0, config)
        assert abs(sum(a*b for a, b in zip(direction, vector))) < 3*Q
    assert wind(unit(SurfacePoint(0, 0, 1)), 0, config) == (0, 0, 0)


def test_upwind_orography_produces_rain_and_leeward_depletion_independent_of_order():
    stencils = (((0, 1),), ((0, 1),), ((1, 1),), ((2, 1),), ((3, 1),))
    retention, ocean, base = (Q,)*5, (Q, 0, 0, 0, 0), (100_000,)*5
    normal = transport(stencils, retention, base, ocean, 12)
    ridge = transport(stencils, retention, (100_000, 100_000, 700_000, 100_000, 100_000), ocean, 12)
    assert ridge[1][2] > normal[1][2] and ridge[1][3] < normal[1][3]
    assert ridge == transport(stencils, retention, (100_000, 100_000, 700_000, 100_000, 100_000), ocean, 12,
                              node_order=reversed(range(5)))
    assert condensation((Q, 0, 0), 0, 2000, ClimateConfig()) > condensation((Q, 0, 0), 0, 0, ClimateConfig())


def test_reference_ocean_controls_maritime_and_source_without_inventing_interior_water():
    config = ClimateConfig(level=3)
    count = len(geometry(3).points)
    ocean = _solve_climate("s", "h", 63_710_000, 0, (-100,)*count, (True,)*count, 12_000_000, config)
    land = _solve_climate("s", "h", 63_710_000, 0, (100,)*count, (False,)*count, 12_000_000, config)
    assert set(ocean.maritime_ppm) == {Q} and set(land.maritime_ppm) == {0}
    assert all(d is None for d in land.ocean_distance_m)
    assert max(map(sum, zip(*land.precipitation_mm))) == 0
    point = SurfacePoint(1, 0, 0)
    assert sample_climate(land, point)["aridity_index_ppm"] == Q
    assert sample_climate(ocean, point)["annual_precipitation_mm"] > 0


def test_roundtrip_replay_order_and_sources_are_unchanged(sources, climate, monkeypatch):
    source, h1 = sources
    before = json.dumps([source.to_dict(), h1.to_dict()], sort_keys=True)
    assert build_climate_plan(source, h1, climate.config) == climate
    def forbidden(*args, **kwargs):
        raise AssertionError("Loading/querying C1 must not globally solve climate")
    monkeypatch.setattr("app.game.world.genesis.climate.plan._solve_climate", forbidden)
    loaded = load_climate_plan(json.loads(json.dumps(climate.to_dict())), source.signature, h1.signature,
                               source.config.radius_m, source.config.sea_level_m)
    assert loaded == climate
    points = geometry(3).points[::13]
    assert {p: sample_climate(climate, p) for p in points} == {p: sample_climate(loaded, p) for p in reversed(points)}
    assert json.dumps([source.to_dict(), h1.to_dict()], sort_keys=True) == before
    with pytest.raises(ValueError):
        build_climate_plan(replace(source, signature="other"), h1)


def test_queries_use_four_vertices_with_regional_altitude_only(sources, climate):
    point = SurfacePoint(13, -4, 7)
    macro = sample_climate(climate, point)
    regional = sample_regional_climate(sources[0], climate, point)
    assert macro["annual_precipitation_mm"] == regional["annual_precipitation_mm"]
    assert regional["resolution"] == "regional_v4_altitude_adjustment"
    assert all(s["precipitation_mm"] >= 0 and s["snowfall_potential_mm"] <= s["precipitation_mm"] for s in regional["seasons"])
    assert sum(s["precipitation_mm"] for s in regional["seasons"]) == regional["annual_precipitation_mm"]
    assert macro["weather_event"] is macro["actual_snowpack_mm"] is macro["permanent_water"] is None
    assert season_at_phase(macro, 0) == season_at_phase(macro, Q)
    assert season_at_phase(macro, 250_000)["temperature_centi_c"] == macro["seasons"][1]["temperature_centi_c"]
    inputs = hydrology_inputs(regional, 1)
    assert inputs["river_discharge_m3_s"] is inputs["perennial"] is inputs["available_runoff_mm"] is None
    assert inputs["precipitation_mm"] == regional["seasons"][1]["precipitation_mm"]
    assert inputs["period_duration_days"] == [360, 4]
    with pytest.raises(ValueError):
        hydrology_inputs(macro, True)


def test_queries_are_continuous_at_face_seams_and_poles(climate):
    probes = [SurfacePoint(1, 1, 0), SurfacePoint(1, -1, 1), SurfacePoint(0, 0, 1), SurfacePoint(0, 0, -1)]
    for point in probes:
        baseline = sample_climate(climate, point)
        for delta in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            for sign in (-1, 1):
                near = SurfacePoint(*(x*2**28+sign*d for x, d in zip(point.xyz, delta)))
                result = sample_climate(climate, near)
                assert abs(result["mean_temperature_centi_c"]-baseline["mean_temperature_centi_c"]) <= 2
                assert abs(result["annual_precipitation_mm"]-baseline["annual_precipitation_mm"]) <= 4
                for a, b in zip(result["seasons"], baseline["seasons"]):
                    assert max(abs(x-y) for x, y in zip(a["wind_vector_milli_m_s"], b["wind_vector_milli_m_s"])) <= 3


def test_version_source_and_invalid_fields_fail_closed(sources, climate):
    for field, value in (("kind", "climate_c2"), ("source_signature", "other"), ("radius_m", 99)):
        data = {**climate.to_dict(), field: value}
        with pytest.raises(ValueError):
            load_climate_plan(data, sources[0].signature, sources[1].signature, climate.radius_m, climate.sea_level_m)
    data = json.loads(json.dumps(climate.to_dict()))
    data["moisture_ppm"][0][0] = -1
    with pytest.raises(ValueError):
        load_climate_plan(data, sources[0].signature, sources[1].signature, climate.radius_m, climate.sea_level_m)


def test_c1_replay_in_processes_with_different_hash_seeds(climate):
    code = ("import json,hashlib; from app.game.world.genesis.formation_plan import build_plan; "
        "from app.game.world.genesis.formation_v4 import FormationConfigV4; "
        "from app.game.world.genesis.hydrology.plan import build_hydrology_plan; "
        "from app.game.world.genesis.hydrology.config import HydrologyConfig; "
        "from app.game.world.genesis.climate.plan import build_climate_plan; "
        "from app.game.world.genesis.climate.config import ClimateConfig; "
        "s=build_plan(42,FormationConfigV4(macro_level=2)); h=build_hydrology_plan(s,HydrologyConfig(level=2)); "
        "c=build_climate_plan(s,h,ClimateConfig(level=3)); "
        "print(hashlib.sha256(json.dumps(c.to_dict(),sort_keys=True).encode()).hexdigest())")
    expected = hashlib.sha256(json.dumps(climate.to_dict(), sort_keys=True).encode()).hexdigest()
    assert expected == "d96c77c026b91fd95f7110d018dd37561e52e584cfc7203ad2506dc24b3fa404"
    for seed in ("1", "1234"):
        assert subprocess.check_output([sys.executable, "-c", code], text=True,
            env={**os.environ, "PYTHONHASHSEED": seed}).strip() == expected


@pytest.mark.parametrize("seed,radius", [(0, 6_371_000), (42, 63_710_000), (2026, 637_100_000), (42, 10**12)])
def test_multiple_planets_no_degeneracy_and_bounded_memory(seed, radius):
    source = build_plan(seed, FormationConfigV4(radius_m=radius, macro_level=2))
    h1 = build_hydrology_plan(source, HydrologyConfig(level=2))
    tracemalloc.start()
    try:
        plan = build_climate_plan(source, h1, ClimateConfig(level=3))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(plan.heights) == 386 and peak < 64*1024*1024
    annual = [sum(p) for p in zip(*plan.precipitation_mm)]
    assert 0 <= min(annual) < max(annual) <= 4320
    assert max(plan.transport_residual_ppm) < 5000
    assert max(plan.maritime_ppm) > min(plan.maritime_ppm)
    assert len(json.dumps(plan.to_dict())) < 200_000


def test_no_pet_does_not_falsely_classify_a_cold_region_as_humid(climate):
    sample = sample_climate(climate, SurfacePoint(0, 0, 1), _terrain_height=20_000)
    assert sample["annual_potential_evapotranspiration_mm"] == 0
    assert sample["aridity_index_ppm"] is sample["precipitation_to_pet_ppm"] is None
    assert sample["aridity_status"] == "energy_limited_undefined"


def test_c1_read_contract_has_a_frozen_versioned_vector(climate):
    sample = sample_climate(climate, SurfacePoint(13, -4, 7))
    assert hashlib.sha256(json.dumps(sample, sort_keys=True).encode()).hexdigest() == (
        "376bf2d195a9a2a4b8eaeea136ae7af4fb46829c301ba33dad8df99a86209592")


def test_local_point_queries_do_not_scan_seasonal_arrays(climate):
    class LimitedReads:
        def __init__(self, values):
            self.values, self.reads = values, 0
        def __getitem__(self, key):
            self.reads += 1
            assert self.reads <= 16, "A point query must read only its four interpolation vertices"
            return self.values[key]
    winds = tuple(LimitedReads(values) for values in climate.wind_milli_m_s)
    restricted = replace(climate, wind_milli_m_s=winds)
    assert sample_climate(restricted, SurfacePoint(1, 2, 3)) == sample_climate(climate, SurfacePoint(1, 2, 3))


def test_offline_climate_preview_and_metrics(climate, tmp_path):
    from PIL import Image
    from app.game.world.genesis.climate.preview import metrics, write_preview
    write_preview(climate, tmp_path, 16)
    with Image.open(tmp_path/"climate.png") as image:
        assert image.size == (1280, 1156)
    report = metrics(climate)
    assert report["vertices"] == 386
    assert 0 < report["weighted_land_fraction"] < 1
    with pytest.raises(ValueError):
        write_preview(climate, tmp_path, 512)
