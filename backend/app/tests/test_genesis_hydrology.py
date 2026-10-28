from dataclasses import replace
import hashlib
import json
import math
import os
import subprocess
import sys

import pytest

from app.game.world.genesis.coast_refinement import _between
from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.drainage import solve, validate
from app.game.world.genesis.hydrology.geometry import AREA_UNIT, geometry
from app.game.world.genesis.hydrology.plan import build_hydrology_plan, load_hydrology_plan
from app.game.world.genesis.hydrology.sectors import corridor_port_id, sector_snapshot
from app.game.world.genesis.sphere_area import cell_solid_angle
from app.game.world.genesis.sphere_topology import CellKey, DIRECTIONS, SurfacePoint, cell_at, neighbor


@pytest.fixture(scope="module")
def source():
    return build_plan(42, FormationConfigV4())


@pytest.fixture(scope="module")
def hydro(source):
    return build_hydrology_plan(source, HydrologyConfig(level=2))


def _graph(heights, edges, areas=None, sills=None):
    heights, edges = tuple(heights), tuple(tuple(sorted(edge)) for edge in edges)
    return solve(heights, edges, tuple(sills or [max(heights[a], heights[b]) for a, b in edges]),
                 tuple(areas or [1]*len(heights)), 0)


def test_confluence_conserves_area_and_strahler_order():
    d = _graph([-5, 1, 3, 5, 6], [(0, 1), (1, 2), (2, 3), (2, 4)])
    assert d.parent == (-1, 0, 1, 2, 2)
    assert d.area == (4, 4, 3, 1, 1)
    assert d.order[2] == 2
    assert all(d.head[p] <= d.head[i] for i, p in enumerate(d.parent) if p >= 0)


def test_depression_is_closed_before_conditional_spill_and_terrain_is_unchanged():
    terrain = (-5, 10, 1, 5)
    d = _graph(terrain, [(0, 1), (1, 2), (2, 3)])
    assert terrain == (-5, 10, 1, 5)
    assert d.raw_outlet[2] == d.raw_outlet[3] == 2
    assert d.head[2] == d.head[3] == 10
    assert d.parent[2] == 1 and d.outlet[2] == 0
    assert d.depressions == ((2, 3),)


def test_connected_reference_ocean_uses_barriers_not_continent_labels():
    d = _graph([-10, -8, -9], [(0, 1), (1, 2)], areas=[10, 2, 1], sills=[-8, 7])
    assert d.marine == (True, True, False)
    assert d.water_components == ((0, 1), (2,))
    assert d.raw_outlet[2] == 2
    assert d.head[2] == 7  # a potential overflow, not an automatically permanent lake


def test_all_land_is_closed_without_inventing_an_ocean_and_all_sea_has_no_runoff():
    land = _graph([8, 2, 5], [(0, 1), (1, 2)])
    assert not any(land.marine) and land.water_components == ()
    assert land.parent[1] == -1 and set(land.outlet) == {1}
    sea = _graph([-8, -2, -5], [(0, 1), (1, 2)])
    assert all(sea.marine) and sum(sea.area) == 0


def test_flat_ties_and_barriers_cannot_create_unexplained_uphill_cycles():
    flat = _graph([-1, 0, 0, 0], [(0, 1), (1, 2), (2, 3), (1, 3)])
    assert flat == _graph([-1, 0, 0, 0], [(1, 3), (2, 3), (1, 2), (0, 1)])
    barrier = _graph([-5, 10, 1], [(0, 1), (1, 2)], sills=[10, 20])
    assert barrier.head[2] == 20 and barrier.raw_parent[2] == -1
    corrupted = replace(flat, parent=(-1, 2, 1, 1))
    with pytest.raises(ValueError):
        validate(corrupted, (-1, 0, 0, 0), ((0, 1), (1, 2), (2, 3), (1, 3)), (0, 0, 0, 0), (1, 1, 1, 1), 0)


@pytest.mark.parametrize("kwargs", [{"level": 6}, {"level": True}, {"hydrology_version": 2},
    {"source_generator_version": 3}, {"channel_min_area_ppm": 0}, {"major_channel_area_ppm": 1}])
def test_hydrology_configuration_fails_closed(kwargs):
    with pytest.raises(ValueError):
        HydrologyConfig(**kwargs)


@pytest.mark.parametrize("level", [2, 3, 5])
def test_graph_geometry_area_and_sample_budget(level):
    g = geometry(level)
    assert len(g.points) == 6*4**level <= 6144
    assert len(g.edges) == 2*len(g.points)
    assert all(len(neighbors) == 4 for neighbors in g.adjacency)
    assert len(set(p for profile in g.profiles for p in profile)) <= 7*len(g.points)
    assert sum(g.area_units)/AREA_UNIT == pytest.approx(4*math.pi, rel=.002)
    key = CellKey(0, level, 0, 0)
    assert g.area_units[0]/AREA_UNIT == pytest.approx(cell_solid_angle(key), rel=.005)


def test_hydrology_does_not_change_formation_or_claim_permanent_water(source, hydro):
    before = json.dumps(source.to_dict(), sort_keys=True)
    assert hydro.source_signature == source.signature
    assert hydro.reaches and hydro.basin_records() and hydro.lake_records() and hydro.closed_basin_records()
    assert all(r["discharge_m3_s"] is None and r["perennial"] is None for r in hydro.network_records())
    assert all(lake["permanent"] is None and lake["volume_available_m3"] is None for lake in hydro.lake_records())
    for source_node in hydro.channel_index:
        edge = hydro.edge_record(source_node)
        profile = edge["potential_head_profile_m"]
        assert all(a >= b for a, b in zip(profile, profile[1:]))
        assert all(h >= z for h, z in zip(profile, edge["sampled_terrain_m"]))
    assert json.dumps(source.to_dict(), sort_keys=True) == before
    with pytest.raises(ValueError):
        build_hydrology_plan(build_plan(42, FormationConfig()), HydrologyConfig(level=2))


def test_plan_roundtrip_process_replay_and_order_independence(source, hydro):
    loaded = load_hydrology_plan(json.loads(json.dumps(hydro.to_dict())), source.signature,
                                  source.config.radius_m, source.config.sea_level_m)
    assert loaded == hydro
    keys = [CellKey(0, 3, 3, 0), CellKey(5, 3, 7, 3), CellKey(2, 3, 1, 2)]
    assert {k: sector_snapshot(hydro, k) for k in keys} == {k: sector_snapshot(loaded, k) for k in reversed(keys)}
    source_code = ("import json,hashlib; from app.game.world.genesis.formation_v4 import FormationConfigV4; "
        "from app.game.world.genesis.formation_plan import build_plan; "
        "from app.game.world.genesis.hydrology.plan import build_hydrology_plan; "
        "from app.game.world.genesis.hydrology.config import HydrologyConfig; "
        "h=build_hydrology_plan(build_plan(42,FormationConfigV4()),HydrologyConfig(level=2)); "
        "print(hashlib.sha256(json.dumps(h.to_dict(),sort_keys=True).encode()).hexdigest())")
    values = [subprocess.check_output([sys.executable, "-c", source_code], text=True,
        env={**os.environ, "PYTHONHASHSEED": h}) for h in ("1", "982")]
    expected = hashlib.sha256(json.dumps(hydro.to_dict(), sort_keys=True).encode()).hexdigest()
    # Pin authoritative H1 decisions as well as replaying them across processes.
    assert expected == "b0e42c91881666cf817cceb7b2e3977c582f8cf6322fac1c15f62789d721da5e"
    assert values[0].strip() == values[1].strip() == expected
    broken = hydro.to_dict()
    broken["config"]["hydrology_version"] = 2
    with pytest.raises(ValueError):
        load_hydrology_plan(broken, source.signature, source.config.radius_m, source.config.sea_level_m)


def _find_seam(hydro):
    g = geometry(hydro.config.level)
    for source_node in hydro.channel_index:
        target = hydro.drainage.parent[source_node]
        if cell_at(g.points[source_node], hydro.config.level).face != cell_at(g.points[target], hydro.config.level).face:
            return source_node, target, g.edge_lookup[tuple(sorted((source_node, target)))]
    raise AssertionError("Fixture requires one cross-face potential corridor")


@pytest.mark.parametrize("sector_level", [5, 13, 24])
def test_corridor_crosses_face_with_exact_shared_ports_and_head_conditions(hydro, sector_level):
    g = geometry(hydro.config.level)
    source, target, edge = _find_seam(hydro)
    port = g.ports[edge]
    # Exact small-integer rays avoid exceeding R1's fixed-point interpolation budget.
    near_a = SurfacePoint(*(a+(2**28-1)*p for a, p in zip(g.points[source].xyz, port.xyz)))
    near_b = SurfacePoint(*((2**28-1)*p+b for p, b in zip(port.xyz, g.points[target].xyz)))
    # For level 24 this ray precision still places us on the neighboring sectors.
    a, b = cell_at(near_a, sector_level), cell_at(near_b, sector_level)
    snapshots = [sector_snapshot(hydro, key) for key in (a, b)]
    identifier = corridor_port_id(hydro, edge, port)
    matching = []
    for snapshot in snapshots:
        candidates = [c for c in snapshot["corridors"] if identifier in (c["entry_port_id"], c["exit_port_id"])]
        assert candidates
        matching.append(candidates[0])
        assert snapshot["actually_fed_watercourses"] == []
    assert matching[0]["edge_id"] == matching[1]["edge_id"]
    assert matching[0]["hydraulic_head_bounds_m"] == matching[1]["hydraulic_head_bounds_m"]
    conditions = [c["entry_head_condition"] if c["entry_port_id"] == identifier else c["exit_head_condition"] for c in matching]
    assert conditions[0] == conditions[1]


def test_confluence_ports_share_junction_identity_across_reaches(hydro):
    g = geometry(hydro.config.level)
    for node in range(len(g.points)):
        incoming = [i for i, p in enumerate(hydro.drainage.parent) if p == node and i in hydro.channel_index]
        if len(incoming) >= 2 and node in hydro.channel_index:
            identifiers = {corridor_port_id(hydro, g.edge_lookup[tuple(sorted((i, node)))], g.points[node]) for i in incoming}
            identifiers.add(corridor_port_id(hydro, g.edge_lookup[tuple(sorted((node, hydro.drainage.parent[node])))], g.points[node]))
            assert identifiers == {hydro.identifier("junction", node)}
            return
    raise AssertionError("Fixture requires a confluence")


@pytest.mark.parametrize("seed,radius", [(0, 6_371_000), (42, 63_710_000), (2026, 637_100_000), (42, 1_000_000_000_000)])
def test_multiple_worlds_have_finite_conserved_potential_without_global_high_resolution(seed, radius):
    source = build_plan(seed, FormationConfigV4(radius_m=radius, macro_level=2))
    h = build_hydrology_plan(source, HydrologyConfig(level=2))
    roots = [i for i, p in enumerate(h.drainage.parent) if p < 0]
    assert sum(h.drainage.area[i] for i in roots) == sum(a for a, m in zip(h.cell_area_m2, h.drainage.marine) if not m)
    assert len(h.heights) == 96
    assert len(json.dumps(h.to_dict())) < 100_000


def test_all_face_edge_profiles_share_exact_boundary_points(hydro):
    from app.game.world.genesis.formation_plan import indexed_cell
    from app.game.world.genesis.sphere_topology import edge_points
    g = geometry(hydro.config.level)
    seams = 0
    for index, (a, b) in enumerate(g.edges):
        ka, kb = indexed_cell(a, g.level), indexed_cell(b, g.level)
        if ka.face == kb.face:
            continue
        da = next(d for d in DIRECTIONS if neighbor(ka, d) == kb)
        db = next(d for d in DIRECTIONS if neighbor(kb, d) == ka)
        assert edge_points(ka, da, 2)[1] == edge_points(kb, db, 2)[1] == g.ports[index]
        assert g.profiles[index][2] == g.ports[index]
        assert g.edge_lookup[(a, b)] == index
        seams += 1
    assert seams == 12*2**g.level


def test_h1_memory_budget_and_offline_preview(source, tmp_path):
    import tracemalloc
    from PIL import Image
    from app.game.world.genesis.hydrology.preview import metrics, write_preview
    geometry.cache_clear()
    tracemalloc.start()
    try:
        plan = build_hydrology_plan(source, HydrologyConfig(level=3))
        _ = plan.channel_index, plan.pool_index
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 64*1024*1024
    assert geometry.cache_info().maxsize == 2
    write_preview(plan, tmp_path, 128)
    with Image.open(tmp_path/"hydrology.png") as image:
        assert image.size == (896, 476)
    summary = metrics(plan, source.config)
    assert summary["area_conserved"]
    assert summary["potential_cross_face_edges"] > 0
    assert summary["water_balance"] == "not_modeled"
    with pytest.raises(ValueError):
        write_preview(plan, tmp_path, 2048)
