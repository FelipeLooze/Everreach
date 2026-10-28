"""Offline bounded multi-seed quality study, never opens game databases."""
import argparse
import json
from pathlib import Path
import time

from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_validation import measure_plan
from app.game.world.genesis.validation_report import case_name, write_case, write_comparison

REFERENCE_SEEDS = (0, 1, 2, 3, 4, 5, 7, 11, 17, 23, 42, 73, 101, 2026, 8675309)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--level", type=int, default=6, choices=range(2, 8))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(REFERENCE_SEEDS))
    parser.add_argument("--radius-m", type=int, default=63_710_000)
    parser.add_argument("--formation-version", type=int, choices=(3, 4), default=3)
    parser.add_argument("--compare-radii", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Reuse matching saved diagnostic cases")
    args = parser.parse_args()
    cases = [(seed, args.radius_m) for seed in dict.fromkeys(args.seeds)]
    if args.compare_radii:
        cases += [(seed, radius) for radius in (6_371_000, 637_100_000) for seed in (0, 42, 2026)]
        cases += [(42, 1_000_000_000_000)]
    results = []
    for i, (seed, radius) in enumerate(dict.fromkeys(cases), start=1):
        directory = args.output/case_name(seed, radius)
        config_class = FormationConfigV4 if args.formation_version == 4 else FormationConfig
        config = config_class(radius_m=radius)
        saved_path = directory/"metrics.json"
        saved = json.loads(saved_path.read_text(encoding="utf-8")) if args.resume and saved_path.exists() else None
        complete = all((directory/name).exists() for name in ("terrain.png", "connectivity.png", "uplift.png", "plan.json"))
        if (complete and saved and saved.get("seed") == seed and saved.get("audit_version") == 1
                and saved.get("config") == config.model_dump(mode="json") and saved.get("diagnostic_level") == args.level):
            result = saved
        else:
            start = time.perf_counter()
            plan = build_plan(seed, config)
            plan_seconds = time.perf_counter()-start
            grid = measure_plan(plan, args.level)
            grid.summary["plan_seconds"] = plan_seconds
            write_case(plan, grid, directory)
            result = grid.summary
        results.append(result)
        print(f"{i}/{len(cases)} seed={seed} R={radius} land={result['weighted_land_fraction']:.3%} diff={result['weighted_macro_disagreement_fraction']:.3%} bodies={result['land_components']}/{result['water_components']}", flush=True)
        write_comparison(results, args.output, args.radius_m)


if __name__ == "__main__":
    main()
