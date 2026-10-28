"""Run alone after validation: matched full C1/C2 preparation, queries and memory."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

from app.game.world.genesis.formation_plan import build_plan, load_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.plan import build_hydrology_plan, load_hydrology_plan
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.geometry import geometry
from app.game.world.genesis.climate.plan import build_climate_plan
from app.game.world.genesis.climate.query import sample_climate, sample_regional_climate
from app.game.world.genesis.climate.v2 import ClimateConfigV2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--measure-memory", action="store_true")
    args = parser.parse_args()
    saved = Path("../artifacts/hydrology-h1/seed-42-r63710000")
    if (saved/"source-plan.json").exists() and (saved/"plan.json").exists():
        data = json.loads((saved/"source-plan.json").read_text())
        source = load_plan(data, data["seed"], FormationConfigV4.model_validate(data["config"]))
        h1 = load_hydrology_plan(json.loads((saved/"plan.json").read_text()), source.signature,
                                 source.config.radius_m, source.config.sea_level_m)
    else:
        source = build_plan(42, FormationConfigV4())
        h1 = build_hydrology_plan(source)
    rows = {version: {"full_preparation_seconds": []} for version in (1, 2)}
    plans = {}
    for repeat in range(args.repetitions):
        for version in ((1, 2) if repeat % 2 == 0 else (2, 1)):
            config = (ClimateConfigV2 if version == 2 else ClimateConfig)()
            geometry.cache_clear()
            start = time.perf_counter()
            plan = build_climate_plan(source, h1, config)
            rows[version]["full_preparation_seconds"].append(time.perf_counter()-start)
            if version in plans:
                assert plan == plans[version]
            plans[version] = plan
    for version, row in rows.items():
        plan = plans[version]
        row["full_preparation_median_seconds"] = statistics.median(row["full_preparation_seconds"])
        row["payload_bytes"] = len(json.dumps(plan.to_dict(), separators=(",", ":")).encode())
        global_times, regional_times = [], []
        points = geometry(5).points
        for point in points[::max(1, len(points)//100)][:100]:
            start = time.perf_counter()
            sample_climate(plan, point)
            global_times.append((time.perf_counter()-start)*1000)
            start = time.perf_counter()
            sample_regional_climate(source, plan, point)
            regional_times.append((time.perf_counter()-start)*1000)
        row["global_query_median_ms"] = statistics.median(global_times)
        row["regional_query_median_ms"] = statistics.median(regional_times)
        if args.measure_memory:
            geometry.cache_clear()
            tracemalloc.start()
            measured = build_climate_plan(source, h1, plan.config)
            retained, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert measured == plan
            row.update(tracemalloc_retained_bytes=retained, tracemalloc_peak_bytes=peak)
        print(json.dumps({"version": version, **row}), flush=True)
    result = {"seed": source.seed, "radius_m": source.config.radius_m, "python": sys.version.split()[0],
        "scope": "Full climate build includes V4 height samples and cold climate geometry; existing V4/H1 excluded. Queries exclude ORM. Memory measured separately, not RSS.",
        "versions": rows, "c2_to_c1_preparation_ratio": rows[2]["full_preparation_median_seconds"]/rows[1]["full_preparation_median_seconds"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
