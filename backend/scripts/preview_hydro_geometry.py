"""Offline G1 comparisons, real HR1 witnesses, local probes and bounded benchmarks."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time
import tracemalloc

from scripts.preview_water import sources
from app.game.world.genesis.hydrology.regional import build_regional_hydrology, regional_signature, RegionalHydrologyConfig
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.water.plan import load_water_plan
from app.game.world.genesis.terrain.field import TerrainSampler, build_terrain_plan, checksum
from app.game.world.genesis.terrain.hydrology import audit_regional_constraints
from app.game.world.genesis.terrain.address import tile_at, level_for_spacing
from app.game.world.genesis.hydro_geometry.plan import build_geometry_plan
from app.game.world.genesis.hydro_geometry.regional import regional_request, boundary_probe_request, compare_boundaries
from app.game.world.genesis.hydro_geometry.geometry import build_geometry
from app.game.world.genesis.hydro_geometry.preview import write_preview, metrics
from app.game.world.genesis.hydro_geometry.water_evidence import water_evidence
from app.game.world.genesis.hydro_geometry.spatial import tile_neighbor
from app.game.world.genesis.formation_tectonics import evaluate
from app.game.world.genesis.hydro_geometry.spatial import between

ROOT = Path(__file__).resolve().parents[2]


def emit(plan, sampler, request, output, *, region=None, title="G1", measure=False):
    start = time.perf_counter()
    data = build_geometry(plan, sampler, request)
    seconds = time.perf_counter()-start
    payload = json.dumps(data, separators=(",", ":"))
    start = time.perf_counter()
    from app.game.world.genesis.hydro_geometry.geometry import validate_geometry
    validate_geometry(plan, request, json.loads(payload))
    load_seconds = time.perf_counter()-start
    benchmark = {"build_seconds": seconds, "load_json_validate_seconds": load_seconds,
        "payload_bytes": len(payload.encode()), "scope": "existing sources and request selection excluded; G1 in-memory, not ORM/RSS"}
    if measure:
        tracemalloc.start()
        measured = build_geometry(plan, TerrainSampler(sampler.plan), request)
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert measured == data
        benchmark.update(tracemalloc_retained_bytes=retained, tracemalloc_peak_bytes=peak)
    legacy_audit = audit_regional_constraints(sampler, plan.hydrology, region) if region else None
    write_preview(data, output, region=region, legacy_audit=legacy_audit, title=title)
    report = {"title": title, "request_id": data["request_id"], **metrics(data), "benchmark": benchmark}
    output.mkdir(parents=True, exist_ok=True)
    (output/"evidence.json").write_text(payload, encoding="utf-8")
    (output/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"title": title, "build_seconds": seconds, "payload_bytes": benchmark["payload_bytes"],
                      "route_statuses": report["route_status_counts"], "geometric_conditions": report["route_geometric_conditions"]}), flush=True)
    return data, report


def run(seed, radius, node, output, *, local=False):
    source, h1, c2 = sources(seed, radius)
    sampler = TerrainSampler(build_terrain_plan(source))
    hr_sig = regional_signature(h1, RegionalHydrologyConfig())
    plan = build_geometry_plan(sampler.plan, h1, hr_sig)
    waterfolder = ROOT/f"artifacts/water-w1/seed-{seed}-r{radius}"
    water = None
    if (waterfolder/"plan.json").exists():
        wd = json.loads((waterfolder/"plan.json").read_text())
        water = load_water_plan(wd, h1, c2, hr_sig)
        evidence = json.loads((waterfolder/"hr1-evidence.json").read_text())
        region = next((r for r in evidence if r["node"] == node), None)
    else:
        region = None
    region = region or build_regional_hydrology(source, h1, node)
    before = [checksum(p) for p in (source.to_dict(), h1.to_dict(), region, c2.to_dict(), water.to_dict() if water else None)]
    folder = output/f"seed-{seed}-r{radius}-node-{node}"
    reports = []
    records = []
    for candidate in (False, True):
        name = "t1-candidate-ports" if candidate else "legacy-ports"
        request = regional_request(plan, sampler, region, candidate_ports=candidate, grid_intervals=16)
        data, report = emit(plan, sampler, request, folder/name, region=region,
            title=f"seed {seed} / R {radius} m / node {node} / {name}", measure=seed == 42 and radius == 63710000 and not candidate)
        records.append(data)
        report.update(seed=seed, radius_m=radius, node=node)
        reports.append(report)
        (folder/name/"w2-input.json").write_text(json.dumps(water_evidence(data, water), separators=(",", ":")), encoding="utf-8")
    audit = audit_regional_constraints(sampler, h1, region, water)
    (folder/"legacy-t1-audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    if local:
        point = geometry(h1.config.level).points[node]
        tile = tile_at(point, level_for_spacing(radius, 2, 8))
        first = boundary_probe_request(plan, sampler, tile, "east", ["west"])
        second_tile = tile_neighbor(tile, "east")
        second = boundary_probe_request(plan, sampler, second_tile, "east", ["west"])
        left, a = emit(plan, sampler, first, folder/"local-a", title=f"seed {seed} local boundary probes A")
        right, b = emit(plan, sampler, second, folder/"local-b", title=f"seed {seed} local boundary probes B")
        (folder/"local-bilateral.json").write_text(json.dumps(compare_boundaries(left, right), indent=2), encoding="utf-8")
        reports.extend([{**a, "seed": seed, "radius_m": radius, "node": node}, {**b, "seed": seed, "radius_m": radius, "node": node}])
    assert [checksum(p) for p in (source.to_dict(), h1.to_dict(), region, c2.to_dict(), water.to_dict() if water else None)] == before
    (folder/"source-preservation.json").write_text(json.dumps({"before_after_checksums": before,
        "sources": ["V4", "H1", "HR1", "C2", "W1"], "all_unchanged": True}, indent=2), encoding="utf-8")
    return reports


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--radius-m", type=int, default=63710000)
    p.add_argument("--node", type=int, default=3982)
    p.add_argument("--output", type=Path, default=ROOT/"artifacts/hydro-geometry-g1")
    args = p.parse_args()
    cases = [(42, 63710000, 3982), (0, 63710000, 874), (2026, 63710000, 141),
             (42, 6371000, 136), (42, 637100000, 37), (42, 10**12, 37)] if args.suite else [(args.seed, args.radius_m, args.node)]
    reports = [report for seed, radius, node in cases for report in run(seed, radius, node, args.output, local=True)]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"suite.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
