"""Bounded offline T1 samples, benchmark and optional read-only W1 compatibility."""
import argparse
import json
from pathlib import Path
import statistics
import time
import tracemalloc

from app.game.world.genesis.formation_plan import build_plan, load_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.formation_tectonics import evaluate
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.hydrology.plan import load_hydrology_plan
from app.game.world.genesis.climate.plan import load_climate_plan
from app.game.world.genesis.water.plan import load_water_plan
from app.game.world.genesis.terrain.config import TerrainConfig
from app.game.world.genesis.terrain.address import level_for_spacing, tile_at
from app.game.world.genesis.terrain.field import TerrainSampler, build_terrain_plan, checksum
from app.game.world.genesis.terrain.patch import prepare_patch
from app.game.world.genesis.terrain.geometry import surface_geometry
from app.game.world.genesis.terrain.hydrology import audit_regional_constraints
from app.game.world.genesis.terrain.preview import write_comparison

ROOT = Path(__file__).resolve().parents[2]


def run(seed, radius, output):
    folder = ROOT/f"artifacts/hydrology-h1/seed-{seed}-r{radius}"
    if (folder/"source-plan.json").exists():
        data = json.loads((folder/"source-plan.json").read_text(encoding="utf-8"))
        source = load_plan(data, seed, FormationConfigV4.model_validate(data["config"]))
    else:
        source = build_plan(seed, FormationConfigV4(radius_m=radius))
    config = TerrainConfig(sample_intervals=32)
    start = time.perf_counter()
    sampler = TerrainSampler(build_terrain_plan(source, config))
    preparation = time.perf_counter()-start
    point = SurfacePoint(3, 2, 1)
    # Prefer an existing W1-fed reference witness, never place or alter geography.
    context, reports = None, []
    waterfolder = ROOT/f"artifacts/water-w1/seed-{seed}-r{radius}"
    if (waterfolder/"plan.json").exists() and (folder/"plan.json").exists():
        h1 = load_hydrology_plan(json.loads((folder/"plan.json").read_text()), source.signature, radius, source.config.sea_level_m)
        climatepath = ROOT/f"artifacts/climate-calibration-0.5.1/seed-{seed}-r{radius}/c2-plan.json"
        if climatepath.exists():
            c2 = load_climate_plan(json.loads(climatepath.read_text()), source.signature, h1.signature, radius, source.config.sea_level_m)
            waterdata = json.loads((waterfolder/"plan.json").read_text())
            water = load_water_plan(waterdata, h1, c2, waterdata["hr_signature"])
            regions = json.loads((waterfolder/"hr1-evidence.json").read_text())
            fed = [i for i in range(len(h1.heights)) if any(p["fluxes"]["outflow"][i] for p in water.solution.periods)
                   and water.support[i] == "bilateral_downhill_validated"]
            if fed:
                point = geometry(h1.config.level).points[fed[0]]
            selected = [r for r in regions if r["node"] in fed][:2] or regions[:2]
            before = checksum(water.to_dict())
            reports = [audit_regional_constraints(sampler, h1, region, water) for region in selected]
            assert checksum(water.to_dict()) == before
            context = {"w1_checksum_before_after": before, "w1_model_fed_nodes": fed,
                       "inspected_regions": [r["node"] for r in selected]}
    tile = tile_at(point, level_for_spacing(radius, 2, config.sample_intervals))
    cold = TerrainSampler(sampler.plan)
    start = time.perf_counter()
    patch = prepare_patch(cold, tile)
    cold_seconds = time.perf_counter()-start
    start = time.perf_counter()
    assert prepare_patch(cold, tile) == patch
    warm_seconds = time.perf_counter()-start
    tracemalloc.start()
    measured = prepare_patch(TerrainSampler(sampler.plan), tile)
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert measured == patch
    timings = []
    macro_timings = []
    for i in range(100):
        p = tile.point(i%33, (i*7)%33, 32)
        start = time.perf_counter()
        cold.sample(p)
        timings.append((time.perf_counter()-start)*1000)
        start = time.perf_counter()
        evaluate(source.seed, source.config, source.plates, p, causes=False)
        macro_timings.append((time.perf_counter()-start)*1000)
    target = output/f"seed-{seed}-r{radius}"
    comparison = write_comparison(sampler, point, target)
    report = {"seed": seed, "radius_m": radius, "descriptor": sampler.plan.to_dict(),
        "witness_point": list(point.xyz), "comparison": comparison, "hydrology_context": context,
        "geometry_witness": surface_geometry(sampler, point),
        "benchmark": {"descriptor_seconds": preparation, "cold_patch_seconds": cold_seconds,
            "warm_patch_seconds": warm_seconds, "sample_query_median_ms": statistics.median(timings),
            "v4_direct_query_median_ms": statistics.median(macro_timings),
            "patch_samples": 1089, "patch_json_bytes": len(json.dumps(patch, separators=(",", ":")).encode()),
            "tracemalloc_retained_bytes": retained, "tracemalloc_peak_bytes": peak,
            "scope": "T1 in-memory only; existing V4/H1/C2/W1, ORM, images excluded; tracemalloc is not RSS"}}
    (target/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (target/"hydrology-constraints.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    (target/"tile.json").write_text(json.dumps(patch, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"seed": seed, "radius_m": radius, **report["benchmark"]}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--radius-m", type=int, default=63_710_000)
    parser.add_argument("--suite", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT/"artifacts/terrain-t1")
    args = parser.parse_args()
    cases = [(0, 63_710_000), (42, 63_710_000), (2026, 63_710_000),
             (42, 6_371_000), (42, 637_100_000), (42, 10**12)] if args.suite else [(args.seed, args.radius_m)]
    results = [run(seed, radius, args.output) for seed, radius in cases]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"suite.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
