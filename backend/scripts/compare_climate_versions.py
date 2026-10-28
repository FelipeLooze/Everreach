"""C1/C2 audit of frozen C1 samples, without resampling or changing terrain."""
import argparse
import json
from pathlib import Path
import statistics
import time
import tracemalloc

from app.game.world.genesis.climate.calibration import report
from app.game.world.genesis.climate.calibration_preview import write_comparison
from app.game.world.genesis.climate.geometry import geometry
from app.game.world.genesis.climate.plan import _solve_climate, load_climate_plan
from app.game.world.genesis.climate.query import sample_climate, sample_regional_climate
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.formation_config import plate_scale_m
from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4


def solve(c1, config):
    return _solve_climate(c1.source_signature, c1.hydrology_signature, c1.radius_m, c1.sea_level_m,
                          c1.heights, c1.marine, plate_scale_m(c1.radius_m), config)


def iteration_sensitivity(output):
    """Check the finite relaxation horizon without changing any default or save."""
    results = []
    for radius in (6_371_000, 63_710_000):
        for version in (1, 2):
            folder = output/f"seed-42-r{radius}"
            data = json.loads((folder/f"c{version}-plan.json").read_text())
            baseline = load_climate_plan(data, data["source_signature"], data["hydrology_signature"], radius, data["sea_level_m"])
            config = type(baseline.config)(**{**baseline.config.model_dump(), "transport_iterations": 64})
            extended = solve(baseline, config)
            before, after = report(baseline), report(extended)
            results.append({"radius_m": radius, "version": version, "iterations": [40, 64],
                "land_precipitation_mm": [r["groups"]["surface/land"]["mean_precipitation_mm"] for r in (before, after)],
                "land_dry_index_fraction": [r["groups"]["surface/land"]["index_area_fractions"]["dry_index"] for r in (before, after)],
                "max_residual_ppm": [max(r["transport_residual_ppm"]) for r in (before, after)]})
    (output/"iteration-sensitivity.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def main():
    parser = argparse.ArgumentParser(description="Requires C1 audit output; never opens a campaign database")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--measure-memory", action="store_true")
    parser.add_argument("--render-seeds", type=int, nargs="*", default=[0, 42, 2026])
    args = parser.parse_args()
    baseline_reports = json.loads((args.output/"c1-comparison.json").read_text())
    comparison = []
    for record in baseline_reports:
        seed, radius = record["seed"], record["radius_m"]
        folder = args.output/f"seed-{seed}-r{radius}"
        data = json.loads((folder/"c1-plan.json").read_text())
        c1 = load_climate_plan(data, data["source_signature"], data["hydrology_signature"], radius, data["sea_level_m"])
        config = ClimateConfigV2(**{**c1.config.model_dump(), "climate_version": 2})
        geometry.cache_clear()
        start = time.perf_counter()
        replayed_c1 = solve(c1, c1.config)
        before_seconds = time.perf_counter()-start
        assert replayed_c1 == c1
        geometry.cache_clear()
        start = time.perf_counter()
        c2 = solve(c1, config)
        after_seconds = time.perf_counter()-start
        assert c2.sea_temperature_centi_c == c1.sea_temperature_centi_c
        assert c2.wind_milli_m_s == c1.wind_milli_m_s and c2.heights == c1.heights
        assert c2.insolation_ppm == c1.insolation_ppm and c2.maritime_ppm == c1.maritime_ppm
        payload = json.dumps(c2.to_dict(), separators=(",", ":"))
        start = time.perf_counter()
        loaded = load_climate_plan(json.loads(payload), c2.source_signature, c2.hydrology_signature, radius, c2.sea_level_m)
        load_seconds = time.perf_counter()-start
        assert loaded == c2
        global_times = []
        for point in geometry(c2.config.level).points[:100]:
            start = time.perf_counter()
            sample_climate(c2, point)
            global_times.append((time.perf_counter()-start)*1000)
        benchmark = {"c1_kernel_cold_seconds": before_seconds, "c2_kernel_cold_seconds": after_seconds,
            "scope": "same pinned terrain samples; excludes V4/H1 and terrain sampling, includes cold climate geometry",
            "c2_load_json_seconds": load_seconds, "c2_payload_bytes": len(payload.encode()),
            "c2_point_query_median_ms": statistics.median(global_times)}
        if seed == 42 and radius == 63_710_000:
            source = build_plan(seed, FormationConfigV4())
            for version, plan in ((1, c1), (2, c2)):
                measurements = []
                for point in geometry(plan.config.level).points[:100]:
                    start = time.perf_counter()
                    sample_regional_climate(source, plan, point)
                    measurements.append((time.perf_counter()-start)*1000)
                benchmark[f"c{version}_regional_query_median_ms"] = statistics.median(measurements)
            if args.measure_memory:
                for version, selected in ((1, c1.config), (2, c2.config)):
                    geometry.cache_clear()
                    tracemalloc.start()
                    measured = solve(c1, selected)
                    retained, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    benchmark[f"c{version}_retained_bytes"] = retained
                    benchmark[f"c{version}_peak_bytes"] = peak
                    assert measured.config == selected
        result = {"seed": seed, "c1": record, "c2": report(c2), "benchmark": benchmark,
                  "temperature_wind_pet_unchanged": True}
        (folder/"c2-plan.json").write_text(payload, encoding="utf-8")
        (folder/"comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        comparison.append(result)
        if seed in args.render_seeds and radius == 63_710_000:
            write_comparison(c1, c2, folder, seed)
        print(json.dumps({"seed": seed, "radius": radius, "c1_land_rain": record["groups"]["surface/land"]["mean_precipitation_mm"],
            "c2_land_rain": result["c2"]["groups"]["surface/land"]["mean_precipitation_mm"],
            "c2_dry_land_fraction": result["c2"]["groups"]["surface/land"]["index_area_fractions"]["dry_index"]}), flush=True)
    (args.output/"comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    data = json.loads((args.output/"seed-42-r63710000/c1-plan.json").read_text())
    c1 = load_climate_plan(data, data["source_signature"], data["hydrology_signature"], data["radius_m"], data["sea_level_m"])
    sensitivity = []
    for gain in (0, 150_000, 250_000, 400_000):
        config = ClimateConfigV2(**{**c1.config.model_dump(), "climate_version": 2, "extratropical_condensation_ppm": gain})
        sensitivity.append({"gain_ppm": gain, **report(solve(c1, config))})
    (args.output/"c2-sensitivity-seed42.json").write_text(json.dumps(sensitivity, indent=2), encoding="utf-8")
    iteration_sensitivity(args.output)


if __name__ == "__main__":
    main()
