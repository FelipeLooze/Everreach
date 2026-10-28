"""Bounded multi-seed C1 audit, before any authoritative calibration changes."""
import argparse
import json
from pathlib import Path
import time

from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.formation_config import plate_scale_m
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.plan import build_climate_plan, load_climate_plan, _solve_climate
from app.game.world.genesis.climate.calibration import report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--quick", action="store_true", help="Audit only the existing seed-42 baseline plus ablations")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    seeds = [42] if args.quick else [*range(13), 42, 2026]
    cases = [(seed, 63_710_000) for seed in seeds]
    if not args.quick:
        cases += [(42, 6_371_000), (42, 637_100_000), (42, 10**12)]
    results = []
    for seed, radius in cases:
        existing = args.output/f"seed-{seed}-r{radius}/c1-plan.json"
        if not existing.exists():
            existing = Path(f"../artifacts/climate-c1/seed-{seed}-r{radius}/plan.json")
        start = time.perf_counter()
        if existing.exists():
            data = json.loads(existing.read_text())
            plan = load_climate_plan(data, data["source_signature"], data["hydrology_signature"], radius, 0)
        else:
            source = build_plan(seed, FormationConfigV4(radius_m=radius))
            h1 = build_hydrology_plan(source)
            plan = build_climate_plan(source, h1)
        result = {"seed": seed, **report(plan), "audit_seconds_including_prerequisites_if_missing": time.perf_counter()-start}
        folder = args.output/f"seed-{seed}-r{radius}"
        folder.mkdir(exist_ok=True)
        (folder/"c1-plan.json").write_text(json.dumps(plan.to_dict(), separators=(",", ":")), encoding="utf-8")
        (folder/"c1-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        results.append(result)
        print(json.dumps({"seed": seed, "radius": radius,
            "land_rain_mm": result["groups"]["surface/land"]["mean_precipitation_mm"],
            "land_dry_fraction": result["groups"]["surface/land"]["index_area_fractions"]["dry_index"],
            "ocean_rain_mm": result["groups"].get("surface/reference_ocean", {}).get("mean_precipitation_mm")}), flush=True)
    (args.output/"c1-comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    baseline = json.loads((args.output/"seed-42-r63710000/c1-plan.json").read_text())
    plan = load_climate_plan(baseline, baseline["source_signature"], baseline["hydrology_signature"], 63_710_000, 0)
    experiments = {"baseline": {}, "no_orography": {"orographic_condensation_ppm_per_km": 0},
        "double_transport_length": {"moisture_length_m": 2*plan.moisture_length_m},
        "double_rain_conversion": {"rain_scale_milli_mm_per_day": 24_000},
        "half_pet": {"pet_scale_milli_mm_per_day": 2250},
        "higher_base_condensation": {"base_condensation_ppm": 150_000}}
    rows = []
    for name, changes in experiments.items():
        config = ClimateConfig(**{**plan.config.model_dump(), **changes})
        alternate = _solve_climate(plan.source_signature, plan.hydrology_signature, plan.radius_m, plan.sea_level_m,
            plan.heights, plan.marine, plate_scale_m(plan.radius_m), config)
        if name == "baseline":
            assert alternate == plan
        rows.append({"experiment": name, "overrides": changes, "diagnostic_only_not_saved_to_campaign": True,
                     **report(alternate)})
    (args.output/"c1-ablations-seed42.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
