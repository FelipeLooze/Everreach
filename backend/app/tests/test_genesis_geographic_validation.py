import json
import math

import pytest

from app.game.world.genesis.coast_refinement import build_coast_patch, fragment_at
from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_geography import sample_at
from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_preview import write_preview
from app.game.world.genesis.formation_validation import grid_geometry, measure_plan, weighted_quantile
from app.game.world.genesis.sphere_area import cell_solid_angle, rectangle_solid_angle
from app.game.world.genesis.sphere_topology import CellKey, DIRECTIONS, SurfacePoint, cell_center, neighbor
from app.game.world.genesis.validation_report import case_name, write_case, write_comparison


@pytest.fixture(scope="module")
def plan():
    return build_plan(42, FormationConfig(macro_level=2))


@pytest.mark.parametrize("level", [0, 1, 3, 5])
def test_cube_cell_area_conserves_whole_sphere_and_is_positive(level):
    n = 2**level
    areas = [cell_solid_angle(CellKey(f, level, x, y)) for f in range(6) for y in range(n) for x in range(n)]
    assert min(areas) > 0
    assert math.fsum(areas) == pytest.approx(4*math.pi, abs=3e-13)
    if level >= 3:
        assert max(areas) > 3*min(areas)  # real distortion, not equal pixel weighting


def test_area_adds_under_subdivision_and_matches_independent_spherical_triangles():
    from app.game.world.genesis.sphere_topology import cell_vertices
    def triangle(a, b, c):
        vectors = [tuple(v/math.hypot(*p.xyz) for v in p.xyz) for p in (a, b, c)]
        a, b, c = vectors
        dot = lambda x, y: sum(i*j for i, j in zip(x, y))
        cross = (b[1]*c[2]-b[2]*c[1], b[2]*c[0]-b[0]*c[2], b[0]*c[1]-b[1]*c[0])
        return 2*math.atan2(abs(dot(a, cross)), 1+dot(a, b)+dot(b, c)+dot(c, a))
    for face in range(6):
        key = CellKey(face, 3, 2, 5)
        children = [CellKey(face, 4, key.x*2+x, key.y*2+y) for y in range(2) for x in range(2)]
        assert sum(cell_solid_angle(c) for c in children) == pytest.approx(cell_solid_angle(key), abs=1e-14)
        a, b, c, d = cell_vertices(key)
        assert triangle(a, b, c)+triangle(a, c, d) == pytest.approx(cell_solid_angle(key), abs=1e-14)


def test_quadrant_and_invalid_area_inputs():
    assert rectangle_solid_angle(-1, -1, 1, 1) == pytest.approx(2*math.pi/3)
    with pytest.raises(ValueError):
        rectangle_solid_angle(1, -1, -1, 1)
    with pytest.raises(ValueError):
        grid_geometry(8)
    assert weighted_quantile([0, 100], [0.9, 0.1], 0.5) == 0


@pytest.mark.parametrize("face", range(6))
def test_tiny_cell_area_uses_stable_triangle_formula(face):
    parent = CellKey(face, 23, 0, 2**23-1)
    area = cell_solid_angle(parent)
    children = [CellKey(face, 24, x, 2*parent.y+y) for x in range(2) for y in range(2)]
    assert min(cell_solid_angle(c) for c in children) > 0
    assert sum(cell_solid_angle(c) for c in children) == pytest.approx(area, rel=1e-12)


def test_weighted_validation_and_original_preview_agree_without_changing_plan(plan, tmp_path):
    before = json.dumps(plan.to_dict(), sort_keys=True)
    grid = measure_plan(plan, 4)
    preview = write_preview(plan, tmp_path/"preview", face_size=16)
    assert grid.summary["weighted_land_fraction"] == pytest.approx(preview["weighted_land_fraction"], abs=1e-12)
    assert grid.summary["weighted_macro_disagreement_fraction"] == pytest.approx(preview["weighted_macro_disagreement_fraction"], abs=1e-12)
    assert grid.summary["solid_angle_sum"] == pytest.approx(4*math.pi)
    assert grid.summary["weighted_land_fraction"]+grid.summary["weighted_water_fraction"] == pytest.approx(1)
    assert json.dumps(plan.to_dict(), sort_keys=True) == before
    case = tmp_path/case_name(plan.seed, plan.config.radius_m)
    grid.summary["plan_seconds"] = 0
    write_case(plan, grid, case)
    write_comparison([grid.summary], tmp_path)
    assert (tmp_path/"reference-terrain.png").exists()
    assert (tmp_path/"comparison.csv").read_text(encoding="utf-8").count("\n") == 2


def test_patch_reproducible_ids_parent_relations_and_budget(plan):
    tile = CellKey(0, 3, 7, 4)
    before = json.dumps(plan.to_dict(), sort_keys=True)
    first = build_coast_patch(plan, tile, 6)
    elsewhere = build_coast_patch(plan, neighbor(tile, "east"), 6)
    second = build_coast_patch(plan, tile, 6)
    assert first == second
    assert json.dumps(plan.to_dict(), sort_keys=True) == before
    assert first["sample_count"] < first["sample_budget"]
    assert sum(len(f["cells"]) for f in first["fragments"]) == first["interior_cells"] == 64
    macro_ids = {c.id for c in plan.components}
    assert all(set(f["macro_coverage_ids"]) <= macro_ids for f in first["fragments"])
    assert all(f["id"].startswith("coast-fragment-r1:") for f in first["fragments"])
    assert first["baseline_only"] and elsewhere["baseline_only"]
    restored = json.loads(json.dumps(first))
    assert restored == first
    for fragment in restored["fragments"]:
        assert fragment_at(restored, cell_center(CellKey(*fragment["cells"][0])))["id"] == fragment["id"]
    with pytest.raises(ValueError):
        fragment_at(restored, cell_center(CellKey(1, 3, 0, 0)))
    with pytest.raises(ValueError):
        build_coast_patch(plan, tile, 9)
    with pytest.raises(ValueError):
        build_coast_patch(plan, CellKey(0, 1, 0, 0), 4)


def test_bounded_noise_cache_is_transparent_across_seeds_and_warm_calls(monkeypatch):
    from app.game.world.genesis import formation_noise
    cached = formation_noise._node_value
    cached.cache_clear()
    assert cached.cache_info().maxsize == 8192
    plans = [build_plan(seed, FormationConfig(macro_level=2)) for seed in (0, 42, 2026)]
    points = [SurfacePoint(1, 1, 0), SurfacePoint(1, -1, 1), SurfacePoint(0, 0, 1), SurfacePoint(-7, 2, 9)]
    warm = [[sample_at(p, point) for point in points] for p in plans]
    before = cached.cache_info().hits
    assert sample_at(plans[1], points[0]) == warm[1][0]
    assert cached.cache_info().hits >= before+48
    monkeypatch.setattr(formation_noise, "_node_value", cached.__wrapped__)
    assert [[sample_at(p, point) for point in points] for p in plans] == warm


def test_maximum_patch_depth_stays_bounded_and_process_replay_matches(plan):
    import os
    import subprocess
    import sys
    patch = build_coast_patch(plan, CellKey(0, 8, 255, 128), 13)
    assert patch["interior_cells"] == 1024
    assert patch["halo_cells"] <= 128
    assert patch["sample_count"] <= 32768
    source = ("import json; from app.game.world.genesis.formation_config import FormationConfig; "
              "from app.game.world.genesis.formation_plan import build_plan; "
              "from app.game.world.genesis.coast_refinement import build_coast_patch; "
              "from app.game.world.genesis.sphere_topology import CellKey; "
              "p=build_plan(42,FormationConfig(macro_level=2)); "
              "print(json.dumps(build_coast_patch(p,CellKey(0,3,7,4),6),sort_keys=True))")
    outputs = [subprocess.check_output([sys.executable, "-c", source], text=True,
               env={**os.environ, "PYTHONHASHSEED": h}) for h in ("1", "23")]
    assert outputs[0] == outputs[1]


def test_exported_refinement_does_not_mutate_persisted_terrain_or_changes(db_session, tmp_path):
    from sqlalchemy.orm import Session
    from app.game.world.seed import create_campaign
    from app.game.world.genesis.service import initialize_world, materialize_sector
    from app.game.world.genesis.formation_plan import load_plan
    from app.db.models.world_genesis import GenesisWorld
    from app.db.models.world_spatial import GenesisSphereSector
    campaign = create_campaign(db_session, "Subordinate only", world_seed=42)
    config = FormationConfig(macro_level=2)
    world = initialize_world(db_session, campaign.id, config)
    terrain = materialize_sector(db_session, campaign.id, CellKey(0, config.sector_level, 0, 0))
    terrain.changes = {"events": ["keep landslide"]}
    before_plan, before_terrain = json.dumps(world.plan, sort_keys=True), json.dumps(terrain.baseline, sort_keys=True)
    patch = build_coast_patch(load_plan(world.plan, 42, config), CellKey(0, 3, 7, 4), 6)
    (tmp_path/"patch.json").write_text(json.dumps(patch), encoding="utf-8")
    campaign_id = campaign.id
    db_session.commit()
    with Session(db_session.get_bind()) as reopened:
        saved = reopened.get(GenesisWorld, campaign_id)
        sector = reopened.get(GenesisSphereSector, (campaign_id, 0, 0, 0))
        assert json.dumps(saved.plan, sort_keys=True) == before_plan
        assert json.dumps(sector.baseline, sort_keys=True) == before_terrain
        assert sector.changes == {"events": ["keep landslide"]}


def test_coast_cli_exports_subordinate_view_with_frozen_macro_ids(plan, tmp_path):
    import subprocess
    import sys
    exported = tmp_path/"plan.json"
    exported.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
    directory = tmp_path/"coast"
    output = subprocess.check_output([sys.executable, "-m", "scripts.preview_planet", "--plan", str(exported),
        "--coast-level", "5", "--coast-tile", "0", "2", "1", "1", "--output", str(directory)], text=True)
    assert json.loads(output)["detail_level"] == 5
    assert (directory/"coast.png").exists()
    patch = json.loads((directory/"patch.json").read_text(encoding="utf-8"))
    assert patch["plan_signature"] == plan.signature
    assert json.loads(exported.read_text()) == json.loads(json.dumps(plan.to_dict()))


@pytest.mark.parametrize("face", range(6))
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_subordinate_ports_are_shared_exactly_across_every_face_seam(plan, face, direction):
    level = 3
    x = 0 if direction == "west" else 7 if direction == "east" else 4
    y = 0 if direction == "south" else 7 if direction == "north" else 4
    tile = CellKey(face, level, x, y)
    other = neighbor(tile, direction)
    a, b = build_coast_patch(plan, tile, level+1), build_coast_patch(plan, other, level+1)
    a_ports, b_ports = {p["id"]: p for p in a["ports"]}, {p["id"]: p for p in b["ports"]}
    shared = a_ports.keys() & b_ports.keys()
    assert len(shared) == 2
    for identifier in shared:
        left, right = a_ports[identifier].copy(), b_ports[identifier].copy()
        # Only ownership of the local fragment differs; the crossing contract does not.
        left.pop("local_fragment_id")
        right.pop("local_fragment_id")
        assert left == right


def test_patch_ports_remain_consistent_at_all_eight_triple_face_vertices(plan):
    for face in (0, 1):
        for x in (0, 7):
            for y in (0, 7):
                tile = CellKey(face, 3, x, y)
                side = neighbor(tile, "west" if x == 0 else "east")
                poleward = neighbor(tile, "south" if y == 0 else "north")
                patches = [build_coast_patch(plan, key, 4) for key in (tile, side, poleward)]
                for first, second in ((0, 1), (0, 2), (1, 2)):
                    a, b = ({p["id"]: p for p in patches[i]["ports"]} for i in (first, second))
                    shared = a.keys() & b.keys()
                    assert len(shared) == 2
                    for identifier in shared:
                        assert a[identifier]["continuous_kind_at_samples"] == b[identifier]["continuous_kind_at_samples"]


def test_shore_brackets_retain_opposite_signs_and_are_shared_across_patches(plan):
    # Find a deterministic real patch containing a v3 shore.
    for x in range(4):
        patch = build_coast_patch(plan, CellKey(0, 2, x, 1), 5)
        if patch["shore_brackets"]:
            break
    assert patch["shore_brackets"]
    for crossing in patch["shore_brackets"]:
        values = [sample_at(plan, SurfacePoint(*p))["elevation_m"] for p in crossing["bracket"]]
        assert values == crossing["elevation_m"]
        assert (values[0] >= plan.config.sea_level_m) != (values[1] >= plan.config.sea_level_m)


def test_narrow_water_channel_creates_subordinate_fragment_without_macro_relabel(plan, monkeypatch):
    # Controlled field fixture: coarse center misses a narrow channel; fine centers see it.
    def channel(seed, config, plates, point, **kwargs):
        v = point.z/point.x
        return {"elevation_m": -100 if abs(v+0.15625) < 0.02 else 100}
    monkeypatch.setattr("app.game.world.genesis.coast_refinement.evaluate", channel)
    patch = build_coast_patch(plan, CellKey(0, 2, 1, 1), 5)
    water = [f for f in patch["fragments"] if f["kind"] == "water"]
    assert water
    assert any(f["open"] for f in water)
    assert any(p["continuous_kind_at_samples"] and p["kind_a"] == p["kind_b"] == "water" for p in patch["ports"])
    assert channel(None, None, None, cell_center(CellKey(0, 2, 1, 1)))["elevation_m"] > 0


def test_quarter_probes_detect_subcell_obstruction_between_same_kind_centers(plan, monkeypatch):
    def thin_channel(seed, config, plates, point, **kwargs):
        return {"elevation_m": -100 if abs(point.z/point.x+0.1875) < 0.005 else 100}
    monkeypatch.setattr("app.game.world.genesis.coast_refinement.evaluate", thin_channel)
    patch = build_coast_patch(plan, CellKey(0, 2, 1, 1), 5)
    assert patch["subcell_obstructions"]
    assert not any(f["kind"] == "water" for f in patch["fragments"])
    assert patch["guarantee"] == "fixed_patch_sample_graph_with_quarter_arc_probes"
