"""Offline W1: fixed explicit HR1 samples, water conservation and seasonal availability."""
import argparse
import json
from pathlib import Path
import statistics
import time
import tracemalloc
from fractions import Fraction

from app.game.world.genesis.formation_plan import build_plan, load_plan, indexed_cell
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.plan import build_hydrology_plan, load_hydrology_plan
from app.game.world.genesis.hydrology.regional import build_regional_hydrology
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.climate.plan import build_climate_plan, load_climate_plan
from app.game.world.genesis.water.plan import build_water_plan, load_water_plan
from app.game.world.genesis.water.preview import metrics, write_preview, write_regional_preview
from app.game.world.genesis.water.query import node_record


def sources(seed, radius):
    folder = Path(f"../artifacts/hydrology-h1/seed-{seed}-r{radius}")
    if (folder/"source-plan.json").exists() and (folder/"plan.json").exists():
        data = json.loads((folder/"source-plan.json").read_text())
        source = load_plan(data, seed, FormationConfigV4.model_validate(data["config"]))
        h1 = load_hydrology_plan(json.loads((folder/"plan.json").read_text()), source.signature, radius, source.config.sea_level_m)
    else:
        source = build_plan(seed, FormationConfigV4(radius_m=radius))
        h1 = build_hydrology_plan(source)
    path = Path(f"../artifacts/climate-calibration-0.5.1/seed-{seed}-r{radius}/c2-plan.json")
    climate = load_climate_plan(json.loads(path.read_text()), source.signature, h1.signature, radius, source.config.sea_level_m) if path.exists() else build_climate_plan(source, h1, ClimateConfigV2())
    return source, h1, climate


def examples(source, h1, climate):
    baseline = build_water_plan(source, h1, climate)
    supply = [sum(p["fluxes"]["local_runoff"][i] for p in baseline.solution.periods) for i in range(len(h1.heights))]
    eligible = [i for i in h1.channel_index if supply[i] > 0]
    def priority(node):
        target = h1.drainage.parent[node]
        storage_free = not any(h1.edge_record(node)["raise_above_sampled_terrain_m"])
        return (not storage_free, -Fraction(supply[node], h1.cell_area_m2[node]), node)
    eligible.sort(key=priority)
    seams = [i for i in eligible if indexed_cell(i, h1.config.level).face != indexed_cell(h1.drainage.parent[i], h1.config.level).face]
    selected = set()
    # This is a technical witness selection, never automatic gameplay placement.
    for node in (seams[:2]+eligible):
        pair = {node, h1.drainage.parent[node]}
        if len(selected | pair) > 32:
            continue
        selected |= pair
        if len(selected) >= 30:
            break
    return [build_regional_hydrology(source, h1, node) for node in sorted(selected)]


def run(seed, radius, args):
    source, h1, climate = sources(seed, radius)
    start = time.perf_counter()
    regions = examples(source, h1, climate) if args.prepare_examples else []
    evidence_seconds = time.perf_counter()-start
    start = time.perf_counter()
    plan = build_water_plan(source, h1, climate, regions)
    elapsed = time.perf_counter()-start
    payload = json.dumps(plan.to_dict(), separators=(",", ":"))
    start = time.perf_counter()
    loaded = load_water_plan(json.loads(payload), h1, climate, plan.hr_signature)
    loading = time.perf_counter()-start
    assert loaded.to_dict() == plan.to_dict()
    samples = []
    for node in range(100):
        start = time.perf_counter()
        node_record(plan, node)
        samples.append((time.perf_counter()-start)*1000)
    benchmark = {"w1_build_seconds": elapsed, "explicit_hr1_preparation_seconds": evidence_seconds,
        "load_json_validate_seconds": loading, "payload_bytes": len(payload.encode()),
        "node_query_median_ms": statistics.median(samples), "scope": "existing V4/H1/C2 excluded; queries in memory, no ORM"}
    if args.measure_memory and seed == 42 and radius == 63710000:
        tracemalloc.start()
        measured = build_water_plan(source, h1, climate, regions)
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert measured.to_dict() == plan.to_dict()
        benchmark.update(tracemalloc_retained_bytes=retained, tracemalloc_peak_bytes=peak)
    output = args.output/f"seed-{seed}-r{radius}"
    write_preview(plan, output, seed)
    report = {"seed": seed, **metrics(plan), "benchmark": benchmark,
        "evidence_scope": "explicit finite witness set, not a census of all regional rivers"}
    if report["model_fed_nodes"]:
        first = report["model_fed_nodes"][0]
        region = next(r for r in regions if r["node"] == first)
        write_regional_preview(plan, region, output)
    (output/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.export_plans:
        (output/"plan.json").write_text(payload, encoding="utf-8")
        (output/"hr1-evidence.json").write_text(json.dumps(regions, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"seed": seed, "radius_m": radius, "build_seconds": elapsed,
        "runoff_mm": report["land_mean_local_runoff_mm"], "model_fed_edges": report["model_fed_sampled_edge_count"],
        "route_counts": report["route_status_counts"], "residual_liters": report["year_residual_liters"]}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description="W1 developer atlas; no saves or public map access")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--radius-m", type=int, default=63710000)
    parser.add_argument("--suite", action="store_true")
    parser.add_argument("--prepare-examples", action="store_true")
    parser.add_argument("--measure-memory", action="store_true")
    parser.add_argument("--export-plans", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [(0,63710000),(42,63710000),(2026,63710000),(42,6371000),(42,637100000),(42,10**12)] if args.suite else [(args.seed,args.radius_m)]
    reports = [run(seed, radius, args) for seed, radius in cases]
    (args.output/"comparison.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
