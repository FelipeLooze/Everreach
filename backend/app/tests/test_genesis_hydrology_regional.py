from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
import subprocess
import sys
import tracemalloc

import pytest

from app.game.world.genesis.formation_plan import build_plan, indexed_cell
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.hydrology.regional import (
    RegionalHydrologyConfig, build_regional_hydrology, compare_regional_connection, regional_sector_snapshot, validate_region,
)
from app.game.world.genesis.hydrology.regional_graph import SampleContext, flood, path_to
from app.game.world.genesis.sphere_topology import CellKey, SurfacePoint, cell_at


@pytest.fixture(scope="module")
def sources():
    source = build_plan(42, FormationConfigV4())
    h1 = build_hydrology_plan(source, HydrologyConfig(level=2))
    return source, h1


def flat_plan(h1):
    # Preserve the real H1 DAG/course membership; inject a controlled terrain fixture.
    return replace(h1, heights=(0,)*len(h1.heights),
                   drainage=replace(h1.drainage, head=(10,)*len(h1.heights)))


@pytest.mark.parametrize("values", [{"depth": 1}, {"depth": 5}, {"depth": True}, {"refinement_version": 2},
                                   {"hydrology_version": 2}, {"refinement_version": True}, {"unknown": 1}])
def test_hr1_config_is_bounded_and_versioned(values):
    with pytest.raises(ValueError):
        RegionalHydrologyConfig(**values)


def test_determinism_order_source_preservation_and_real_v4_paths(sources):
    source, h1 = sources
    old = json.dumps([source.to_dict(), h1.to_dict()], sort_keys=True)
    nodes = [5, 16, 80]
    a = {n: build_regional_hydrology(source, h1, n) for n in nodes}
    b = {n: build_regional_hydrology(source, h1, n) for n in reversed(nodes)}
    assert a == b
    assert json.dumps([source.to_dict(), h1.to_dict()], sort_keys=True) == old
    assert all(r["segments"] for r in a.values())
    for region in a.values():
        validate_region(json.loads(json.dumps(region)))
        assert region["actually_fed_watercourses"] == []
        assert region["water_balance"]["precipitation"] is None
        assert all(p["perennial"] is None for p in region["ports"])
        assert region["budget"]["graph_count"] <= 5
        assert region["budget"]["sample_count"] <= 12000


@pytest.mark.parametrize("level", [5, 13, 24])
def test_shared_port_and_head_across_faces_and_fine_sectors(sources, level):
    source, original = sources
    h1, g = flat_plan(original), geometry(original.config.level)
    node = next(i for i in h1.channel_index if indexed_cell(i, 2).face != indexed_cell(h1.drainage.parent[i], 2).face)
    target = h1.drainage.parent[node]
    regions = [build_regional_hydrology(source, h1, n, _sampler=lambda p: 0) for n in (node, target)]
    ports = [next(p for p in r["ports"] if p["source_node"] == node) for r in regions]
    assert ports[0] == ports[1]
    assert compare_regional_connection(*regions, ports[0]["id"])["status"] == "connected_sampled_potential"
    port = SurfacePoint(*ports[0]["point"])
    snapshots = []
    for n, region in zip((node, target), regions):
        near = SurfacePoint(*(a+(2**28-1)*b for a, b in zip(g.points[n].xyz, port.xyz)))
        snapshots.append(regional_sector_snapshot(region, cell_at(near, level)))
    conditions = []
    for snapshot in snapshots:
        pieces = [p for p in snapshot["pieces"] if ports[0]["id"] in (p["entry_port_id"], p["exit_port_id"])]
        assert pieces
        piece = pieces[0]
        conditions.append(piece["entry_head_condition"] if piece["entry_port_id"] == ports[0]["id"]
                          else piece["exit_head_condition"])
    assert conditions[0] == conditions[1] == {"kind": "exact_sampled_potential_head", "head_m": 10}


def test_confluences_have_one_receiver_and_common_head(sources):
    source, original = sources
    h1 = flat_plan(original)
    node = next(n for n in h1.channel_index if sum(h1.drainage.parent[i] == n for i in h1.channel_index) >= 2)
    region = build_regional_hydrology(source, h1, node, _sampler=lambda p: 0)
    assert not region["issues"]
    assert len(region["routes"]) >= 3
    receiver = {s["source_vertex"]: s["target_vertex"] for s in region["segments"]}
    assert len(receiver) == len(region["segments"])
    assert any(sum(s["target_vertex"] == target for s in region["segments"]) >= 2
               for target in receiver)
    validate_region(region)


def test_obstacle_refuses_macro_without_incision_or_fictitious_path(sources):
    source, original = sources
    h1 = flat_plan(original)
    centers = set(geometry(2).points)
    region = build_regional_hydrology(source, h1, 5, _sampler=lambda p: 0 if p in centers else 20)
    assert region["issues"] and not region["segments"]
    assert all(p["minimum_required_head_m"] == 20 and p["status"] == "incompatible_h1_head" for p in region["ports"])
    assert all(not r["segment_ids"] for r in region["routes"])


def test_minimax_search_detours_around_sampled_ridge(sources):
    source, _ = sources
    context = SampleContext(source, 2, lambda p: 0)
    graph = context.graph(CellKey(0, 2, 1, 1))
    root = graph.center
    neighbor = graph.adjacent[root][0]
    edge = tuple(sorted((root, neighbor)))
    graph.profiles[edge] = (0, 0, 50, 0, 0)
    costs, parents, _ = flood(graph, root, 0)
    route = path_to(neighbor, root, parents)
    assert costs[neighbor][0] == 0 and len(route) > 2
    assert tuple(sorted((route[0], route[1]))) != edge


def test_closed_storage_is_potential_not_permanent_water(sources):
    source, original = sources
    bottom = geometry(2).points[16]
    region = build_regional_hydrology(source, flat_plan(original), 16, _sampler=lambda p: 0 if p == bottom else 1)
    assert any(any(s["storage_raise_m"]) for s in region["segments"])
    assert region["depression_candidates"]
    assert all(d["permanent"] is None and d["volume_available_m3"] is None for d in region["depression_candidates"])


def test_validator_rejects_broken_heads_cycles_and_boundaries(sources):
    source, h1 = sources
    baseline = build_regional_hydrology(source, h1, 16)
    for kind in ("head", "cycle", "port", "version", "address"):
        data = deepcopy(baseline)
        if kind == "head":
            data["segments"][0]["potential_head_profile_m"][2] = -100000
        elif kind == "cycle":
            data["segments"][0]["target_vertex"] = data["segments"][0]["source_vertex"]
        elif kind == "port":
            data["ports"][0]["potential_head_m"] = 10**9
        elif kind == "version":
            data["refinement_version"] = 2
        else:
            data["node"] += 1
        with pytest.raises(ValueError):
            validate_region(data)


def test_process_replay_and_no_global_h1_recalculation(sources, monkeypatch):
    source, h1 = sources
    def forbidden(*args, **kwargs):
        raise AssertionError("Regional preparation must not rerun global drainage")
    monkeypatch.setattr("app.game.world.genesis.hydrology.plan.solve", forbidden)
    region = build_regional_hydrology(source, h1, 5)
    expected = hashlib.sha256(json.dumps(region, sort_keys=True).encode()).hexdigest()
    code = ("import json,hashlib; from app.game.world.genesis.formation_plan import build_plan; "
        "from app.game.world.genesis.formation_v4 import FormationConfigV4; "
        "from app.game.world.genesis.hydrology.plan import build_hydrology_plan; "
        "from app.game.world.genesis.hydrology.config import HydrologyConfig; "
        "from app.game.world.genesis.hydrology.regional import build_regional_hydrology; "
        "s=build_plan(42,FormationConfigV4()); h=build_hydrology_plan(s,HydrologyConfig(level=2)); "
        "r=build_regional_hydrology(s,h,5); print(hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest())")
    for seed in ("1", "987"):
        actual = subprocess.check_output([sys.executable, "-c", code], text=True,
                                         env={**os.environ, "PYTHONHASHSEED": seed})
        assert actual.strip() == expected


@pytest.mark.parametrize("radius,depth", [(6_371_000, 2), (63_710_000, 4), (1_000_000_000_000, 3)])
def test_scale_memory_and_fixed_work_budget(radius, depth):
    source = build_plan(2026, FormationConfigV4(radius_m=radius, macro_level=2))
    plan = build_hydrology_plan(source, HydrologyConfig(level=2))
    node = next(iter(plan.channel_index))
    tracemalloc.start()
    try:
        region = build_regional_hydrology(source, plan, node, RegionalHydrologyConfig(depth=depth))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 64*1024*1024
    assert region["budget"]["sample_count"] <= 12000
    assert len(json.dumps(region)) < 1_000_000


def test_invalid_sources_addresses_and_excess_graphs_fail_closed(sources):
    source, h1 = sources
    for node in (-1, True, 6144):
        with pytest.raises(ValueError):
            build_regional_hydrology(source, h1, node)
    with pytest.raises(ValueError):
        build_regional_hydrology(replace(source, signature="different"), h1, 5)
    context = SampleContext(source, 2, lambda p: 0)
    for node in range(5):
        context.graph(indexed_cell(node, 2))
    with pytest.raises(ValueError, match="budget"):
        context.graph(indexed_cell(5, 2))


def test_empty_region_has_no_arbitrary_springs_or_preparation(sources):
    source, h1 = sources
    incident = set(h1.channel_index) | {h1.drainage.parent[n] for n in h1.channel_index}
    empty = next(n for n in range(len(h1.heights)) if n not in incident)
    region = build_regional_hydrology(source, h1, empty)
    assert region["segments"] == region["ports"] == region["routes"] == []
    assert region["budget"]["sample_count"] == region["budget"]["graph_count"] == 0


def test_bilateral_inspection_does_not_treat_unresolved_halves_as_connected(sources):
    source, h1 = sources
    node = 5
    target = h1.drainage.parent[node]
    first = build_regional_hydrology(source, h1, node)
    second = build_regional_hydrology(source, h1, target)
    port = next(p for p in first["ports"] if p["source_node"] == node)
    # A persisted unresolved side must remain distinguishable even with a shared port.
    second = deepcopy(second)
    second["segments"] = []
    for route in second["routes"]:
        route["status"], route["segment_ids"] = "local_confluence_conflict", []
    connection = compare_regional_connection(first, second, port["id"])
    assert connection["status"] == "refinement_incompatible" and connection["actual_wet_state"] is None
    second["ports"][0]["point"][0] += 1
    with pytest.raises(ValueError):
        compare_regional_connection(first, second, port["id"])


def test_regional_viewer_is_offline_and_outputs_a_comparison(sources, tmp_path):
    from PIL import Image
    from app.game.world.genesis.hydrology.regional_preview import write_regional_preview
    source, h1 = sources
    region = build_regional_hydrology(source, h1, 16)
    write_regional_preview(source, h1, region, tmp_path)
    with Image.open(tmp_path/"regional.png") as image:
        assert image.size == (764, 582)


def test_worst_case_context_budget_and_profiles_are_integer(sources):
    source, _ = sources
    context = SampleContext(source, 4, lambda p: 0)
    graphs = [context.graph(indexed_cell(n, 2)) for n in range(5)]
    assert all(len(g.points) == 285 and len(g.profiles) == 480 for g in graphs)
    assert len(context.samples) <= 5*(285+3*480) < 12000
    assert all(type(h) is int for g in graphs for p in g.profiles.values() for h in p)
