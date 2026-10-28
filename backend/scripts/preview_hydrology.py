"""Offline: python -m scripts.preview_hydrology --suite --output ../artifacts/hydrology-h1"""
import argparse
import json
from pathlib import Path
import statistics
import time
import tracemalloc

from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.hydrology.plan import build_hydrology_plan, load_hydrology_plan
from app.game.world.genesis.hydrology.preview import export_records, metrics, write_preview
from app.game.world.genesis.hydrology.sectors import sector_snapshot
from app.game.world.genesis.sphere_topology import cell_at


def run(seed, radius, args):
    build_plan.cache_clear()
    geometry.cache_clear()
    start = time.perf_counter()
    source = build_plan(seed, FormationConfigV4(radius_m=radius))
    formation_seconds = time.perf_counter()-start
    start = time.perf_counter()
    plan = build_hydrology_plan(source, HydrologyConfig(level=args.level))
    build_seconds = time.perf_counter()-start
    payload = json.dumps(plan.to_dict(), separators=(",", ":"))
    start = time.perf_counter()
    loaded = load_hydrology_plan(json.loads(payload), source.signature, radius, source.config.sea_level_m)
    load_seconds = time.perf_counter()-start
    assert loaded.to_dict() == plan.to_dict()
    # Cold derived indexes are included in first query, reported separately.
    keys = [cell_at(p, source.config.sector_level) for p in geometry(args.level).points[:100]]
    start = time.perf_counter()
    sector_snapshot(loaded, keys[0])
    first_query_seconds = time.perf_counter()-start
    times = []
    for key in keys:
        start = time.perf_counter()
        sector_snapshot(loaded, key)
        times.append(time.perf_counter()-start)
    result = {"seed": seed, **metrics(plan, source.config), "benchmark": {
        "formation_cold_seconds": round(formation_seconds, 4), "hydrology_cold_seconds": round(build_seconds, 4),
        "load_json_validate_seconds": round(load_seconds, 4), "payload_bytes": len(payload.encode()),
        "first_sector_query_seconds": round(first_query_seconds, 6),
        "sector_query_median_ms": round(statistics.median(times)*1000, 4),
        "sector_query_max_ms": round(max(times)*1000, 4), "sector_queries": len(times)}}
    output = args.output/f"seed-{seed}-r{radius}"
    write_preview(plan, output)
    if args.export_plans:
        export_records(plan, output)
        (output/"plan.json").write_text(payload, encoding="utf-8")
        (output/"source-plan.json").write_text(json.dumps(source.to_dict(), separators=(",", ":")), encoding="utf-8")
    if args.measure_memory and seed == 42 and radius == 63_710_000:
        geometry.cache_clear()
        tracemalloc.start()
        measured = build_hydrology_plan(source, HydrologyConfig(level=args.level))
        _ = measured.channel_index, measured.pool_index
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result["benchmark"].update(tracemalloc_retained_bytes=retained, tracemalloc_peak_bytes=peak,
            memory_scope="separate H1 build + cold geometry + derived indexes, excludes existing source V4")
    (output/"summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description="Bounded H1 developer diagnostics; never opens a database")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--radius-m", type=int, default=63_710_000)
    parser.add_argument("--level", type=int, choices=range(2, 6), default=5)
    parser.add_argument("--suite", action="store_true")
    parser.add_argument("--measure-memory", action="store_true")
    parser.add_argument("--export-plans", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = [(args.seed, args.radius_m)] if not args.suite else [(0, 63_710_000), (42, 63_710_000),
        (2026, 63_710_000), (42, 6_371_000), (42, 637_100_000), (42, 1_000_000_000_000)]
    results = [run(seed, radius, args) for seed, radius in cases]
    (args.output/"comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
