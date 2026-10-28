import json
import subprocess
import sys
import tracemalloc
from dataclasses import replace

import pytest
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_tectonics import evaluate
from app.game.world.genesis.sphere_topology import CellKey, DIRECTIONS, SurfacePoint, edge_points, neighbor
from app.game.world.genesis.terrain.config import TerrainConfig
from app.game.world.genesis.terrain.address import TerrainTile, point_on_face, tile_at, level_for_spacing
from app.game.world.genesis.terrain.field import TerrainSampler, build_terrain_plan, checksum
from app.game.world.genesis.terrain.patch import prepare_patch


@pytest.fixture(scope="module")
def source():
    return build_plan(42, FormationConfigV4(macro_level=2))


@pytest.fixture()
def sampler(source):
    return TerrainSampler(build_terrain_plan(source))


def test_order_lod_and_canonical_rays(sampler):
    tile = TerrainTile(0, 16, 21000, 33000)
    a = prepare_patch(sampler, tile)
    child = TerrainTile(0, 17, tile.x*2, tile.y*2)
    b = prepare_patch(sampler, child)
    fresh = TerrainSampler(sampler.plan)
    assert prepare_patch(fresh, child) == b
    assert prepare_patch(fresh, tile) == a
    for y in range(9):
        for x in range(9):
            assert a["height_mm"][y][x] == b["height_mm"][2*y][2*x]
    p = tile.point(3, 7, 16)
    assert sampler.sample(p) == sampler.sample(SurfacePoint(*(v*2 for v in p.xyz)))


@pytest.mark.parametrize("face", range(6))
def test_all_face_edges_and_vertices(sampler, face):
    level, n = 5, 32
    # Height function is chart independent, including both polar charts and corners.
    for key in (CellKey(face, level, 0, 0), CellKey(face, level, n-1, n-1)):
        for direction in DIRECTIONS:
            other = neighbor(key, direction)
            shared = set(edge_points(key, direction, 4))
            peer = set(p for d in DIRECTIONS for p in edge_points(other, d, 4))
            assert shared <= peer
            for p in shared:
                assert sampler.sample(p)["height_mm"] == TerrainSampler(sampler.plan).sample(p)["height_mm"]
    # Direct aliases from all incident cube charts collapse to exactly the same ray.
    corner = point_on_face(face, 0, 0, 1)
    aliases = {point_on_face(f, u, v, 1) for f in range(6) for u in (0, 1) for v in (0, 1)}
    assert corner in aliases


def test_adjacent_tiles_identical_edges(sampler):
    a, b = TerrainTile(1, 14, 100, 200), TerrainTile(1, 14, 101, 200)
    pa, pb = prepare_patch(sampler, a), prepare_patch(sampler, b)
    assert [r[-1] for r in pa["height_mm"]] == [r[0] for r in pb["height_mm"]]


def test_base_reconstruction_anchors_and_coast_bound(sampler):
    n = 2**sampler.plan.base_level
    for face in range(6):
        for x, y in ((0, 0), (n//3, n//2), (n, n)):
            p = point_on_face(face, x, y, n)
            value = sampler.sample(p)
            raw = evaluate(sampler.plan.source.seed, sampler.plan.source.config, sampler.plan.source.plates, p)["elevation_m"]
            assert value["base_v4_reconstructed_mm"] == raw*1000
            assert abs(value["detail_mm"]) <= 441_000
            assert (value["height_mm"] >= 0) == (value["base_v4_reconstructed_mm"] >= 0)


def test_seam_limit_no_height_jump_and_local_detail(sampler):
    # Approach same physical seam from either chart, with exact high precision rays.
    d = 2**40
    seam = point_on_face(0, d, d//3, d)
    values = [sampler.sample(p)["height_mm"] for p in (seam,
        point_on_face(0, d-1, d//3, d), SurfacePoint(d-1, d, -d//3))]
    assert max(values)-min(values) <= 3
    tile = tile_at(SurfacePoint(3, 2, 1), level_for_spacing(sampler.plan.source.config.radius_m, 5))
    grid = prepare_patch(sampler, tile)
    assert len({v for row in grid["detail_mm"] for v in row}) > 30
    assert max(abs(a-b) for row in grid["height_mm"] for a, b in zip(row, row[1:])) < 30_000


@pytest.mark.parametrize("seed,radius", [(0, 6_371_000), (42, 63_710_000), (2026, 637_100_000), (42, 10**12)])
def test_scale_budget_and_no_global_grid(seed, radius):
    source = build_plan(seed, FormationConfigV4(macro_level=2, radius_m=radius))
    sampler = TerrainSampler(build_terrain_plan(source))
    level = level_for_spacing(radius, 2)
    tile = tile_at(SurfacePoint(3, 2, 1), level)
    tracemalloc.start()
    patch = prepare_patch(sampler, tile)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 16_000_000
    assert patch["max_sample_spacing_m_upper_bound"] <= 2
    assert sampler.cache_size() <= 2048
    assert len(json.dumps(patch)) < sampler.plan.config.max_patch_bytes
    assert len({v for row in patch["detail_mm"] for v in row}) > 5
    if radius == 10**12:
        assert level > 24
        assert tile.physical_ancestor(source.config.sector_level).level == source.config.sector_level


def test_preflight_budgets_and_versions(source):
    from app.game.world.genesis.formation_config import FormationConfig
    for kwargs in ({"terrain_version": True}, {"terrain_version": 2}, {"sample_intervals": True}, {"relief_scale_ppm": -1}):
        with pytest.raises(ValueError):
            TerrainConfig(**kwargs)
    with pytest.raises(ValueError):
        build_terrain_plan(replace(source, config=FormationConfig(macro_level=2)))
    with pytest.raises(ValueError, match="sample budget"):
        prepare_patch(TerrainSampler(build_terrain_plan(source, TerrainConfig(max_patch_samples=25))), TerrainTile(0, 16, 0, 0))
    with pytest.raises(ValueError, match="span budget"):
        prepare_patch(TerrainSampler(build_terrain_plan(source)), TerrainTile(0, 0, 0, 0))
    with pytest.raises(ValueError):
        TerrainTile(0, True, 0, 0)


def test_process_replay_and_golden(sampler):
    p = SurfacePoint(1234567, 1000000, -333333)
    record = sampler.sample(p)
    code = """from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.terrain.field import *
from app.game.world.genesis.sphere_topology import SurfacePoint
s=TerrainSampler(build_terrain_plan(build_plan(42, FormationConfigV4(macro_level=2))))
print(checksum(s.sample(SurfacePoint(1234567,1000000,-333333))))"""
    from pathlib import Path
    value = subprocess.check_output([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2], text=True).strip()
    assert value == checksum(record)
    assert checksum(record) == "4c5cf3e421d620903505ad7560cfcaa4841dff9e6a7330fcc7a04e40a3fb993d"


def test_limits_from_both_sides_of_every_cube_edge_and_corner(sampler):
    points = {p for face in range(6) for direction in DIRECTIONS
              for p in edge_points(CellKey(face, 0, 0, 0), direction, 4)}
    for point in points:
        # Rays share the same limiting surface point, without chart ownership tricks.
        ray = tuple(v*2**40 for v in point.xyz)
        maximum = max(map(abs, ray))
        tied = [i for i, v in enumerate(ray) if abs(v) == maximum]
        heights = [sampler.sample(SurfacePoint(*ray))["height_mm"]]
        for owner in tied:
            approaching = tuple(v if k == owner or k not in tied else v-(1 if v > 0 else -1)
                                for k, v in enumerate(ray))
            heights.append(sampler.sample(SurfacePoint(*approaching))["height_mm"])
        assert max(heights)-min(heights) <= 3


def test_geometry_uses_authoritative_height_and_physical_probe(sampler):
    from app.game.world.genesis.terrain.geometry import surface_geometry
    p = SurfacePoint(3, 2, 1)
    g = surface_geometry(sampler, p)
    assert g["height_mm"] == sampler.sample(p)["height_mm"]
    assert 0 <= g["slope_magnitude_ppm"] < 2_000_000
    assert len(g["gradient_tangent_ppm"]) == 2
    assert g["material_assignment"] is None
    with pytest.raises(ValueError):
        surface_geometry(sampler, p, True)


def test_technical_comparison_artifact(sampler, tmp_path):
    from PIL import Image
    from app.game.world.genesis.terrain.preview import write_comparison
    records = write_comparison(sampler, SurfacePoint(3, 2, 1), tmp_path)
    assert [r["scale"] for r in records] == ["MACRO", "REGIONAL", "LOCAL"]
    assert all(r["sample_count"] == 289 for r in records)
    assert records[-1]["sample_spacing_upper_m"] <= 2
    with Image.open(tmp_path/"terrain-comparison.png") as image:
        assert image.size == (1600, 1460)


def test_corner_cache_eviction_preserves_height(sampler):
    point = SurfacePoint(3, 2, 1)
    before = sampler.sample(point)
    n = 2**sampler.plan.base_level
    for i in range(1100):
        sampler.base(point_on_face(i%6, (i*19)%n, (i*31)%n, n))
    assert sampler.cache_size() == 2048
    assert sampler.sample(point) == before
