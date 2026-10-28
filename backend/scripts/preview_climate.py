"""Offline C1: python -m scripts.preview_climate --suite --output ../artifacts/climate-c1"""
import argparse
import json
from pathlib import Path
import statistics
import time
import tracemalloc

from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.climate.geometry import geometry
from app.game.world.genesis.climate.plan import build_climate_plan, load_climate_plan
from app.game.world.genesis.climate.preview import write_preview, write_summary
from app.game.world.genesis.climate.query import sample_climate, sample_regional_climate


def run(seed, radius, args):
    build_plan.cache_clear()
    start = time.perf_counter()
    source = build_plan(seed, FormationConfigV4(radius_m=radius))
    h1 = build_hydrology_plan(source)
    prerequisites = time.perf_counter()-start
    geometry.cache_clear()
    config = (ClimateConfigV2 if args.climate_version == 2 else ClimateConfig)(level=args.level)
    start = time.perf_counter()
    plan = build_climate_plan(source, h1, config)
    elapsed = time.perf_counter()-start
    payload = json.dumps(plan.to_dict(), separators=(",", ":"))
    start = time.perf_counter()
    loaded = load_climate_plan(json.loads(payload), source.signature, h1.signature, radius, source.config.sea_level_m)
    load_seconds = time.perf_counter()-start
    assert loaded == plan
    times, regional_times = [], []
    for point in geometry(args.level).points[:100]:
        start = time.perf_counter()
        sample_climate(plan, point)
        times.append((time.perf_counter()-start)*1000)
        start = time.perf_counter()
        sample_regional_climate(source, plan, point)
        regional_times.append((time.perf_counter()-start)*1000)
    benchmark = {"v4_h1_preparation_seconds": round(prerequisites, 5), "climate_cold_seconds": round(elapsed, 5),
        "load_json_validate_seconds": round(load_seconds, 5), "payload_bytes": len(payload.encode()),
        "query_global_median_ms": round(statistics.median(times), 5),
        "query_regional_median_ms": round(statistics.median(regional_times), 5),
        "query_scope": "100 in-memory samples; regional includes one authoritative V4 evaluation; excludes ORM"}
    if args.measure_memory and seed == 42 and radius == 63_710_000:
        geometry.cache_clear()
        tracemalloc.start()
        measured = build_climate_plan(source, h1, config)
        retained, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert measured == plan
        benchmark.update(tracemalloc_retained_bytes=retained, tracemalloc_peak_bytes=peak,
                         memory_scope="C1 build plus cold climate geometry, excludes existing V4/H1 and images")
    output = args.output/f"seed-{seed}-r{radius}"
    write_preview(plan, output, args.sample_size)
    if args.export_plans:
        (output/"plan.json").write_text(payload, encoding="utf-8")
    result = {"seed": seed, **write_summary(plan, output, benchmark)}
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description="C1 technical climate atlas; never opens a save")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--radius-m", type=int, default=63_710_000)
    parser.add_argument("--level", type=int, choices=(3, 4, 5), default=5)
    parser.add_argument("--climate-version", type=int, choices=(1, 2), default=1)
    parser.add_argument("--sample-size", type=int, choices=range(16, 97), default=48)
    parser.add_argument("--suite", action="store_true")
    parser.add_argument("--measure-memory", action="store_true")
    parser.add_argument("--export-plans", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [(0, 63_710_000), (42, 63_710_000), (2026, 63_710_000), (42, 6_371_000),
             (42, 637_100_000), (42, 10**12)] if args.suite else [(args.seed, args.radius_m)]
    results = [run(seed, radius, args) for seed, radius in cases]
    (args.output/"comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
