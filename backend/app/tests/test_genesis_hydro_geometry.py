from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import json
import pytest

from app.game.world.genesis.formation_plan import build_plan, indexed_cell
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.terrain.field import TerrainSampler, build_terrain_plan, checksum
from app.game.world.genesis.terrain.address import TerrainTile, tile_at, chart
from app.game.world.genesis.sphere_topology import SurfacePoint, DIRECTIONS
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.regional import build_regional_hydrology, regional_signature, RegionalHydrologyConfig
from app.game.world.genesis.hydro_geometry.plan import build_geometry_plan
from app.game.world.genesis.hydro_geometry.config import G1Config, Anchor, GeometryRequest
from app.game.world.genesis.hydro_geometry.geometry import build_geometry, validate_geometry
from app.game.world.genesis.hydro_geometry.regional import regional_request, compare_boundaries
from app.game.world.genesis.hydro_geometry.spatial import tile_neighbor, edge_points, vertex_areas_mm2, between
from app.game.world.genesis.hydro_geometry.sections import section_curve


@pytest.fixture(scope="module")
def foundation():
    source = build_plan(42, FormationConfigV4(macro_level=2))
    h1 = build_hydrology_plan(source, HydrologyConfig(level=2))
    terrain = build_terrain_plan(source)
    plan = build_geometry_plan(terrain, h1, regional_signature(h1, RegionalHydrologyConfig()), G1Config(section_step_m=1))
    return source, h1, terrain, plan


class AnalyticFixture:
    """Explicit synthetic surface used only to exercise geometric causes."""
    def __init__(self, terrain, tile, function):
        self.plan, self.tile, self.function = terrain, tile, function

    def sample(self, point):
        _, u, v, d = chart(point, self.tile.face)
        x = (Fraction(u*2**self.tile.level, d)-self.tile.x)*8
        y = (Fraction(v*2**self.tile.level, d)-self.tile.y)*8
        return {"height_mm": int(self.function(x, y))}


def request(tile, *, n=8, head=None, target=10, sample_budget=8192, expansion_budget=4096):
    return GeometryRequest(tile=list(vars(tile).values()), grid_intervals=n, target_spacing_m=target,
        sample_budget=sample_budget, expansion_budget=expansion_budget,
        anchors=[Anchor(id="in-west", point=list(tile.point(0, 4, 8).xyz), role="ingress"),
                 Anchor(id="out-east", point=list(tile.point(8, 4, 8).xyz), role="outlet", reference_head_mm=head)])


def test_descending_geometry_replay_order_and_no_water(foundation):
    _, _, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    sampler = AnalyticFixture(terrain, tile, lambda x, y: 10000-x*1000+(y-4)**2*100)
    first = build_geometry(plan, sampler, request(tile))
    req = request(tile)
    reverse = GeometryRequest.model_validate({**req.model_dump(), "anchors": list(reversed(req.anchors))})
    assert first == build_geometry(plan, sampler, reverse)
    route = first["routes"][0]
    assert route["status"] == "verified_at_requested_resolution"
    assert route["sampled_uphill_mm"] == 0
    assert all(z == 0 for z in route["storage_raise_mm"])
    assert first["active_watercourses"] == [] and first["water_volume_liters"] is None
    assert not first["terrain_modified"] and not first["water_ledger_modified"]


def test_obstacle_detour_does_not_excavate(foundation):
    _, _, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    def field(x, y):
        return 10000-x*1000+(y-4)**2*100+(20000 if Fraction(14, 5) < x < Fraction(26, 5) and 1 < y < Fraction(11, 2) else 0)
    data = build_geometry(plan, AnalyticFixture(terrain, tile, field), request(tile))
    path = data["routes"][0]["path_vertices"]
    assert max(v//9 for v in path) >= 6
    assert max(data["routes"][0]["terrain_profile_mm"]) < 20000
    assert all(s["river_bed_excavated"] is False for s in data["segments"])


def test_confluence_tree_has_no_double_receiver_or_new_spring(foundation):
    _, _, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    req = request(tile)
    req = GeometryRequest.model_validate({**req.model_dump(), "anchors": [req.anchors[1].model_dump(),
        Anchor(id="in-north", point=list(tile.point(0, 6, 8).xyz), role="ingress").model_dump(),
        Anchor(id="in-south", point=list(tile.point(0, 2, 8).xyz), role="ingress").model_dump()]})
    data = build_geometry(plan, AnalyticFixture(terrain, tile, lambda x, y: 10000-x*1000+(y-4)**2*100), req)
    assert data["confluences"]
    sources = [s["source_vertex"] for s in data["segments"]]
    assert len(sources) == len(set(sources))
    assert all(r["new_spring"] is False for r in data["routes"])


def test_storage_depression_spill_hypsometry_and_contours(foundation):
    _, _, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    sampler = AnalyticFixture(terrain, tile, lambda x, y: ((x-4)**2+(y-4)**2)*1000)
    req = request(tile)
    req = GeometryRequest.model_validate({**req.model_dump(), "anchors": [req.anchors[1].model_dump(),
        Anchor(id="existing-relay", point=list(tile.point(4, 4, 8).xyz), role="relay").model_dump()]})
    data = build_geometry(plan, sampler, req)
    assert data["routes"][0]["status"] == "partially_verified_storage_required"
    basins = data["depression_geometry"]["depressions"]
    assert basins and any(b["spill_edges"] and b["contour_crossing_brackets"] for b in basins)
    for basin in basins:
        assert basin["spill_height_mm"] > basin["bottom_height_mm"]
        volumes = [p["potential_storage_liters"] for p in basin["potential_hypsometry"]]
        assert volumes == sorted(volumes)
        assert basin["water_volume_liters"] is basin["permanent"] is None


def test_fixed_endpoint_incompatibility_is_distinct_from_resolution_and_budget(foundation):
    _, _, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 13)
    sampler = AnalyticFixture(terrain, tile, lambda x, y: 10000-x*1000)
    incompatible = build_geometry(plan, sampler, request(tile, head=1999))
    assert incompatible["routes"][0]["status"] == "incompatible_fixed_boundary_head"
    assert incompatible["routes"][0]["endpoint_head_violations"][0]["excess_mm"] == 1
    coarse = build_geometry(plan, sampler, request(tile, target=1))
    assert coarse["routes"][0]["status"] == "pending_resolution"
    tiny = build_geometry(plan, sampler, request(tile, sample_budget=16))
    assert tiny["status"] == "pending_budget" and tiny["budget"]["sample_count"] == 16
    short = build_geometry(plan, sampler, request(tile, expansion_budget=1))
    assert short["routes"][0]["status"] == "pending_budget"
    assert short["depression_geometry"]["status"] == "pending_budget"


def test_sections_are_topographic_area_not_discharge():
    result = section_curve([4000, 1000, 0, 1000, 4000], 1000)
    assert result["status"] == "sampled_banked_section"
    assert result["stage_geometry"][0]["cross_section_area_mm2"] == 1_000_000
    assert result["stage_geometry"][0]["connected_width_mm"] == 2000
    assert result["actual_width_mm"] is result["actual_depth_mm"] is result["discharge_capacity_m3_s"] is None
    assert section_curve([0, 0, 1000, 0, 0], 1000)["status"] == "no_enclosed_section_demonstrated"


@pytest.mark.parametrize("face", range(6))
def test_fine_addresses_shared_edges_faces_and_symmetric_profiles(face):
    tile = TerrainTile(face, 35, 0, 0)
    for side in DIRECTIONS:
        peer = tile_neighbor(tile, side)
        shared = set(edge_points(tile, side, 8))
        other = set(p for direction in DIRECTIONS for p in edge_points(peer, direction, 8))
        assert shared <= other
        a, b = sorted(shared, key=lambda p: p.xyz)[0], sorted(shared, key=lambda p: p.xyz)[-1]
        assert [between(a, b, i) for i in range(5)] == [between(b, a, i) for i in range(4, -1, -1)]


def test_regional_candidate_ports_match_across_cube_seam(foundation):
    _, h1, terrain, plan = foundation
    source = terrain.source
    node = next(i for i in h1.channel_index if indexed_cell(i, h1.config.level).face != indexed_cell(h1.drainage.parent[i], h1.config.level).face)
    target = h1.drainage.parent[node]
    sampler = TerrainSampler(terrain)
    a, b = [build_regional_hydrology(source, h1, i) for i in (node, target)]
    ar, br = [regional_request(plan, sampler, r, candidate_ports=True) for r in (a, b)]
    common = {p.id for p in ar.anchors} & {p.id for p in br.anchors}
    assert common
    for identifier in common:
        assert next(p.point for p in ar.anchors if p.id == identifier) == next(p.point for p in br.anchors if p.id == identifier)
    left, right = build_geometry(plan, sampler, ar), build_geometry(plan, sampler, br)
    compared = compare_boundaries(left, right)
    assert compared["shared_boundaries"] and not compared["water_ledger_modified"]
    assert all(not p["active_water_transfer"] for p in compared["shared_boundaries"])


def test_coastal_disagreement_is_versioned_and_does_not_export(foundation):
    source, _, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    before = checksum(source.to_dict())
    data = build_geometry(plan, AnalyticFixture(terrain, tile, lambda x, y: -1), request(tile))
    assert data["coast"]["legacy_t1_disagreements"] > 0
    assert data["coast"]["legacy_v4_r1_labels_preserved"]
    assert data["coast"]["ocean_export_authorized"] is False
    assert checksum(source.to_dict()) == before


def test_validation_and_persistence_budget(foundation):
    _, _, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    sampler = TerrainSampler(terrain)
    for kwargs in ({"geometry_version": True}, {"geometry_version": 2}, {"max_samples": -1}):
        with pytest.raises(ValueError):
            G1Config(**kwargs)
    data = build_geometry(plan, sampler, request(tile))
    corrupt = deepcopy(data)
    corrupt["geometry_version"] = 2
    with pytest.raises(ValueError):
        validate_geometry(plan, request(tile), corrupt)
    small = build_geometry_plan(terrain, plan.hydrology, plan.hr_signature, G1Config(max_payload_bytes=4096))
    compact = build_geometry(small, sampler, request(tile))
    assert compact["status"] == "pending_persistence_budget" and compact["graph"] is None
    assert len(json.dumps(compact, separators=(",", ":")).encode()) < 4096
    with pytest.raises(ValueError, match="matching"):
        build_geometry_plan(terrain, replace(plan.hydrology, source_signature="wrong"), plan.hr_signature)


def test_inherited_anchor_keeps_identity_and_height_across_lods(foundation):
    _, _, terrain, plan = foundation
    parent = tile_at(SurfacePoint(3, 2, 1), 20)
    child = TerrainTile(parent.face, 21, parent.x*2+1, parent.y*2+1)
    req = request(parent)
    inherited = req.anchors[1]
    child_req = GeometryRequest(tile=list(vars(child).values()), anchors=[inherited,
        Anchor(id="child-ingress", point=list(child.point(0, 4, 8).xyz), role="ingress")])
    sampler = TerrainSampler(terrain)
    a, b = build_geometry(plan, sampler, req), build_geometry(plan, sampler, child_req)
    point = inherited.point
    assert a["request"]["anchors"][1]["id"] == b["request"]["anchors"][1]["id"] == inherited.id
    az = a["graph"]["heights_mm"][a["graph"]["points"].index(point)]
    bz = b["graph"]["heights_mm"][b["graph"]["points"].index(point)]
    assert az == bz == sampler.sample(SurfacePoint(*point))["height_mm"]


def test_bilateral_local_geometry_verified_across_face_seam(foundation):
    _, _, terrain, plan = foundation
    from app.game.world.genesis.hydro_geometry.regional import boundary_probe_request
    tile = TerrainTile(0, 23, 2**23-1, 4000000)
    peer = tile_neighbor(tile, "east")
    class SeamFixture:
        plan = terrain
        def sample(self, point):
            return {"height_mm": -(point.y-point.x)*10**12//max(map(abs, point.xyz))}
    sampler = SeamFixture()
    a = boundary_probe_request(plan, sampler, tile, "east", ["west"], target_spacing_m=1)
    b = boundary_probe_request(plan, sampler, peer, "east", ["west"], target_spacing_m=1)
    left, right = build_geometry(plan, sampler, a), build_geometry(plan, sampler, b)
    comp = compare_boundaries(left, right)
    assert comp["shared_boundaries"][0]["status"] == "bilateral_sampled_geometry_verified"


@pytest.mark.parametrize("seed,radius", [(0, 6_371_000), (42, 63_710_000), (2026, 637_100_000), (42, 10**12)])
def test_giant_scale_bounded_memory(seed, radius):
    import tracemalloc
    from app.game.world.genesis.terrain.address import level_for_spacing
    source = build_plan(seed, FormationConfigV4(radius_m=radius, macro_level=2))
    h1 = build_hydrology_plan(source, HydrologyConfig(level=2))
    terrain = build_terrain_plan(source)
    plan = build_geometry_plan(terrain, h1, regional_signature(h1, RegionalHydrologyConfig()))
    tile = tile_at(SurfacePoint(3, 2, 1), level_for_spacing(radius, 2, 8))
    sampler = TerrainSampler(terrain)
    tracemalloc.start()
    data = build_geometry(plan, sampler, request(tile, n=8))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 32_000_000
    assert data["budget"]["sample_count"] <= 8192
    assert data["graph"] and data["grid_spacing_upper_bound_m"] <= 2
    assert len(json.dumps(data)) < plan.config.max_payload_bytes


def test_process_determinism_and_versioned_golden(foundation):
    import subprocess
    import sys
    from pathlib import Path
    source, h1, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    record = build_geometry(plan, TerrainSampler(terrain), request(tile, n=4))
    code = """from app.tests.test_genesis_hydro_geometry import *
s=build_plan(42,FormationConfigV4(macro_level=2))
h=build_hydrology_plan(s,HydrologyConfig(level=2))
t=build_terrain_plan(s)
p=build_geometry_plan(t,h,regional_signature(h,RegionalHydrologyConfig()),G1Config(section_step_m=1))
tile=tile_at(SurfacePoint(3,2,1),20)
print(checksum(build_geometry(p,TerrainSampler(t),request(tile,n=4))))"""
    value = subprocess.check_output([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2], text=True).strip()
    assert value == checksum(record)
    assert value == "aa4e213144b6754c51298284fd421eab4243679676a9f5eeb75bba83b949cd70"


def test_missing_neighbor_and_technical_image_are_not_physical_blockage(foundation, tmp_path):
    from PIL import Image
    from app.game.world.genesis.hydro_geometry.preview import write_preview
    _, _, terrain, plan = foundation
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    data = build_geometry(plan, TerrainSampler(terrain), request(tile, n=4))
    missing = compare_boundaries(data, None)
    assert missing["status"] == "neighbor_evidence_pending"
    assert not missing["physical_blockage_proved"]
    write_preview(data, tmp_path)
    with Image.open(tmp_path/"geometry.png") as image:
        assert image.size == (1600, 1240)


def test_dual_areas_account_for_cube_spherical_distortion():
    from app.game.world.genesis.sphere_topology import CellKey
    from app.game.world.genesis.sphere_area import cell_solid_angle
    radius = 63_710_000
    for tile in (TerrainTile(0, 2, 0, 0), TerrainTile(4, 2, 1, 2)):
        areas = vertex_areas_mm2(tile, 8, radius)
        exact = cell_solid_angle(CellKey(*vars(tile).values()))*radius**2*10**6
        assert abs(sum(areas)-exact)/exact < .002
