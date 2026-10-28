"""Isolated, explicit offline benchmarks; no game save writes or background loop."""
import argparse
import cProfile
import json
from pathlib import Path
import pstats
import statistics
import time
import tracemalloc

from app.game.world.genesis.coast_preview import choose_coast_tile, write_coast_preview
from app.game.world.genesis.coast_refinement import build_coast_patch
from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.formation_geography import generate_sector
from app.game.world.genesis.formation_plan import build_plan, load_plan
from app.game.world.genesis.sphere_topology import CellKey
from app.game.world.genesis.formation_validation import grid_geometry
from app.game.world.genesis.formation_noise import _node_value


def measure(call):
    started = time.perf_counter()
    value = call()
    return value, time.perf_counter()-started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--radii", type=int, nargs="+", default=[6_371_000, 63_710_000, 637_100_000, 1_000_000_000_000])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--formation-version", type=int, choices=(3, 4), default=3)
    parser.add_argument("--geometry-only", action="store_true", help="Trace maximum offline grid allocation instead of generation")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.geometry_only:
        grid_geometry.cache_clear()
        tracemalloc.start()
        try:
            geometry, seconds = measure(lambda: grid_geometry(7))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        result = {"diagnostic_level": 7, "point_count": len(geometry[0]), "python_peak_bytes": peak,
                  "elapsed_seconds_with_tracemalloc": seconds, "geometry_cache_limit": grid_geometry.cache_info().maxsize,
                  "scope": "offline geometry allocation, not game RSS or terrain generation"}
        (args.output/"geometry-memory.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
        return
    results = []
    for radius in args.radii:
        build_plan.cache_clear()
        _node_value.cache_clear()
        config_class = FormationConfigV4 if args.formation_version == 4 else FormationConfig
        config = config_class(radius_m=radius)
        plan, plan_seconds = measure(lambda: build_plan(args.seed, config))
        exported = json.dumps(plan.to_dict())
        _, warm_seconds = measure(lambda: build_plan(args.seed, config))
        loads, sectors = [], []
        n = 2**config.sector_level
        for i in range(12):
            _, seconds = measure(lambda: load_plan(json.loads(exported), plan.seed, config))
            loads.append(seconds)
            key = CellKey(i%6, config.sector_level, (i*7919)%n, (i*3571)%n)
            baseline, seconds = measure(lambda: generate_sector(plan, key))
            sectors.append(seconds)
        detail_level = max(config.macro_level, config.sector_level)
        tile_level = max(config.macro_level, detail_level-5)
        tile = choose_coast_tile(plan, tile_level)
        patch, patch_seconds = measure(lambda: build_coast_patch(plan, tile, detail_level))
        # Trace new allocations of an uncached operation; exclude module imports.
        tracemalloc.start()
        _node_value.cache_clear()
        try:
            _, traced_seconds = measure(lambda: build_coast_patch(plan, tile, detail_level))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        profiler = cProfile.Profile()
        profiler.enable()
        for i in range(12):
            generate_sector(plan, CellKey(i%6, config.sector_level, (i*7919)%n, (i*3571)%n))
        profiler.disable()
        stats = pstats.Stats(profiler)
        hotspots = sorted(({"function": f"{Path(key[0]).name}:{key[1]}:{key[2]}", "calls": value[1],
                            "self_seconds": value[2], "cumulative_seconds": value[3]}
                           for key, value in stats.stats.items()), key=lambda row: row["cumulative_seconds"], reverse=True)[:15]
        result = {"seed": args.seed, "generator_version": config.generator_version,
            "radius_m": radius, "sector_level": config.sector_level,
            "plan_seconds_cold": plan_seconds, "plan_seconds_cached": warm_seconds, "plan_json_bytes": len(exported.encode()),
            "deserialize_and_load_plan_ms_median": statistics.median(loads)*1000,
            "sector_ms_median": statistics.median(sectors)*1000, "sector_ms_max_of_12": max(sectors)*1000,
            "last_sector_json_bytes": len(json.dumps(baseline).encode()),
            "patch_seconds": patch_seconds, "patch_samples": patch["sample_count"],
            "patch_python_peak_bytes": peak, "patch_seconds_with_tracemalloc": traced_seconds,
            "noise_cache": _node_value.cache_info()._asdict(),
            "profile_hotspots": hotspots}
        write_coast_preview(plan, patch, args.output/f"coast-r-{radius}")
        results.append(result)
        (args.output/"benchmarks.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "profile_hotspots"}), flush=True)


if __name__ == "__main__":
    main()
