from dataclasses import fields, replace
import hashlib
import json
import math
import os
import subprocess
import sys
import tracemalloc

import pytest

from app.game.world.genesis.climate.calibration import area_weights, report, transport_audit
from app.game.world.genesis.climate.calibration_preview import write_comparison
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.dispatch import parse_climate_config
from app.game.world.genesis.climate.geometry import Q, geometry, unit
from app.game.world.genesis.climate.physics import condensation as condensation_c1, sine_mdeg, transport
from app.game.world.genesis.climate.plan import build_climate_plan, load_climate_plan, _solve_climate
from app.game.world.genesis.climate.query import sample_climate, sample_regional_climate, hydrology_inputs, season_at_phase
from app.game.world.genesis.climate.v2 import ClimateConfigV2, condensation
from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.sphere_topology import SurfacePoint


@pytest.fixture(scope="module")
def sources():
    source = build_plan(42, FormationConfigV4(macro_level=2))
    return source, build_hydrology_plan(source, HydrologyConfig(level=2))


@pytest.fixture(scope="module")
def c2(sources):
    return build_climate_plan(*sources, ClimateConfigV2(level=3))


@pytest.mark.parametrize("data", [{"climate_version": 4}, {"climate_version": True}, {"climate_version": "2"},
    {"climate_version": 2, "extratropical_condensation_ppm": -1},
    {"climate_version": 2, "extratropical_condensation_ppm": 700001},
    {"climate_version": 2, "level": 6}])
def test_explicit_dispatch_and_invalid_calibration(data):
    with pytest.raises(ValueError):
        parse_climate_config(data)


def test_c1_and_zero_gain_c2_have_identical_physics(sources):
    c1 = build_climate_plan(*sources, ClimateConfig(level=3))
    zero = build_climate_plan(*sources, ClimateConfigV2(level=3, extratropical_condensation_ppm=0))
    for field in fields(c1):
        if field.name not in ("config", "signature"):
            assert getattr(c1, field.name) == getattr(zero, field.name)
    assert c1.to_dict()["kind"] == "climate_c1" and zero.to_dict()["kind"] == "climate_c2"
    assert c1.signature != zero.signature
    assert hashlib.sha256(json.dumps(c1.to_dict(), sort_keys=True).encode()).hexdigest() == (
        "d96c77c026b91fd95f7110d018dd37561e52e584cfc7203ad2506dc24b3fa404")


def test_c2_changes_only_condensation_related_fields(sources, c2):
    source, h1 = sources
    before = json.dumps([source.to_dict(), h1.to_dict()], sort_keys=True)
    c1 = build_climate_plan(source, h1, ClimateConfig(level=3))
    for name in ("heights", "marine", "ocean_distance_m", "maritime_ppm", "sea_temperature_centi_c",
                 "insolation_ppm", "wind_milli_m_s"):
        assert getattr(c2, name) == getattr(c1, name)
    assert c2.precipitation_mm != c1.precipitation_mm
    point = SurfacePoint(1, 0, 1)
    a, b = sample_climate(c1, point), sample_climate(c2, point)
    assert a["annual_potential_evapotranspiration_mm"] == b["annual_potential_evapotranspiration_mm"]
    assert json.dumps([source.to_dict(), h1.to_dict()], sort_keys=True) == before


def test_extratropical_ascent_has_compact_prescribed_support():
    config = ClimateConfigV2()
    for z in (0, sine_mdeg(config.hadley_edge_mdeg), Q, -Q):
        direction = (math.isqrt(Q*Q-z*z), 0, z)
        assert condensation(direction, 0, 0, config) == condensation_c1(direction, 0, 0, config)
    peak = sine_mdeg(config.polar_edge_mdeg)
    assert condensation((0, 0, peak), 0, 0, config)-condensation_c1((0, 0, peak), 0, 0, config) == 250000
    assert condensation((0, 0, -peak), 0, 0, config) == condensation((0, 0, peak), 0, 0, config)
    assert condensation((0, 0, peak), 0, 100000, config) == 850000


def test_c2_needs_an_ocean_source_and_preserves_rain_shadow_rule():
    config = ClimateConfigV2(level=3)
    count = len(geometry(3).points)
    dry = _solve_climate("source", "h1", 63710000, 0, (100,)*count, (False,)*count, 12000000, config)
    assert all(value == 0 for season in dry.precipitation_mm for value in season)
    direction = unit(SurfacePoint(1, 0, 1))
    flat = condensation(direction, 0, 0, config)
    ridge = condensation(direction, 0, 2000, config)
    stencils = (((0, 1),), ((0, 1),), ((1, 1),), ((2, 1),))
    a = transport(stencils, (Q,)*4, (flat,)*4, (Q, 0, 0, 0), 8)
    b = transport(stencils, (Q,)*4, (flat, flat, ridge, flat), (Q, 0, 0, 0), 8)
    assert b[1][2] > a[1][2] and b[1][3] < a[1][3]
    assert b == transport(stencils, (Q,)*4, (flat, flat, ridge, flat), (Q, 0, 0, 0), 8, node_order=(3, 2, 1, 0))


def test_c2_continuity_seasons_contract_and_regional_queries(sources, c2):
    for point in (SurfacePoint(1, 1, 0), SurfacePoint(1, 1, 1), SurfacePoint(0, 0, 1), SurfacePoint(0, 0, -1)):
        a = sample_climate(c2, point)
        for delta in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            b = sample_climate(c2, SurfacePoint(*(2**28*v+d for v, d in zip(point.xyz, delta))))
            assert abs(a["annual_precipitation_mm"]-b["annual_precipitation_mm"]) <= 4
            assert abs(a["mean_temperature_centi_c"]-b["mean_temperature_centi_c"]) <= 2
        assert season_at_phase(a, 0) == season_at_phase(a, Q)
        data = hydrology_inputs(a, 1)
        assert data["kind"] == "climatological_water_balance_inputs_c2"
        assert data["available_runoff_mm"] is data["perennial"] is data["lake_permanent"] is None
    point = SurfacePoint(13, -4, 7)
    assert sample_regional_climate(sources[0], c2, point)["annual_precipitation_mm"] == sample_climate(c2, point)["annual_precipitation_mm"]


def test_c2_roundtrip_order_replay_and_provenance(sources, c2, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("C2 load/query cannot rerun global climate")
    monkeypatch.setattr("app.game.world.genesis.climate.plan._solve_climate", forbidden)
    loaded = load_climate_plan(json.loads(json.dumps(c2.to_dict())), c2.source_signature, c2.hydrology_signature,
                               c2.radius_m, c2.sea_level_m)
    assert loaded == c2
    points = geometry(3).points[::29]
    assert {p: sample_climate(c2, p) for p in points} == {p: sample_climate(loaded, p) for p in reversed(points)}
    data = c2.to_dict()
    data["kind"] = "climate_c1"
    with pytest.raises(ValueError):
        load_climate_plan(data, c2.source_signature, c2.hydrology_signature, c2.radius_m, c2.sea_level_m)


def test_c2_process_replay(c2):
    code = ("import json,hashlib; from app.game.world.genesis.formation_plan import build_plan; "
        "from app.game.world.genesis.formation_v4 import FormationConfigV4; "
        "from app.game.world.genesis.hydrology.plan import build_hydrology_plan; "
        "from app.game.world.genesis.hydrology.config import HydrologyConfig; "
        "from app.game.world.genesis.climate.plan import build_climate_plan; "
        "from app.game.world.genesis.climate.v2 import ClimateConfigV2; "
        "s=build_plan(42,FormationConfigV4(macro_level=2)); h=build_hydrology_plan(s,HydrologyConfig(level=2)); "
        "c=build_climate_plan(s,h,ClimateConfigV2(level=3)); "
        "print(hashlib.sha256(json.dumps(c.to_dict(),sort_keys=True).encode()).hexdigest())")
    expected = hashlib.sha256(json.dumps(c2.to_dict(), sort_keys=True).encode()).hexdigest()
    assert expected == "cc59c620da16da5367e9671f50bc736eb22f0ea16c21d5118abc10f812eeaa90"
    for seed in ("1", "998"):
        assert subprocess.check_output([sys.executable, "-c", code], text=True,
            env={**os.environ, "PYTHONHASHSEED": seed}).strip() == expected


@pytest.mark.parametrize("seed,radius", [(0, 6371000), (42, 63710000), (2026, 637100000), (42, 10**12)])
def test_c2_bounded_memory_scale_and_seed_variation(seed, radius):
    source = build_plan(seed, FormationConfigV4(radius_m=radius, macro_level=2))
    h1 = build_hydrology_plan(source, HydrologyConfig(level=2))
    tracemalloc.start()
    try:
        plan = build_climate_plan(source, h1, ClimateConfigV2(level=3))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 64*1024*1024 and len(plan.heights) == 386
    assert 0 <= min(map(sum, zip(*plan.precipitation_mm))) < max(map(sum, zip(*plan.precipitation_mm)))
    assert max(plan.transport_residual_ppm) < 5000


def test_diagnostics_conserve_area_separate_surfaces_and_show_climate_indices(c2):
    result = report(c2)
    surfaces = [value for key, value in result["groups"].items() if key.startswith("surface/")]
    assert sum(v["solid_angle"] for v in surfaces) == pytest.approx(4*math.pi)
    assert sum(area_weights(3)) == pytest.approx(4*math.pi)
    for value in surfaces:
        assert sum(value["index_area_fractions"].values()) == pytest.approx(1)
        assert sum(value["period_precipitation_mm"]) == pytest.approx(value["mean_precipitation_mm"])
    assert "latitude/land/30-45" in result["groups"] and "altitude/0-500m" in result["groups"]
    assert len(result["transport_audit"]) == 4


def test_comparison_images_and_source_guard(sources, c2, tmp_path):
    from PIL import Image
    c1 = build_climate_plan(*sources, ClimateConfig(level=3))
    write_comparison(c1, c2, tmp_path, 42, 16)
    with Image.open(tmp_path/"aridity-comparison.png") as image:
        assert image.size == (1088, 520)
    assert len(list(tmp_path.glob("*.png"))) == 7
    with pytest.raises(ValueError):
        write_comparison(c1, replace(c2, source_signature="other"), tmp_path, 42)
