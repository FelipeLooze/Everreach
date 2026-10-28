"""Bounded technical witness near a historical V4 shore; not coast generation."""
import json
from pathlib import Path
from scripts.preview_water import sources
from scripts.preview_hydro_geometry import emit
from app.game.world.genesis.formation_tectonics import evaluate
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.hydrology.regional import regional_signature, RegionalHydrologyConfig
from app.game.world.genesis.terrain.field import TerrainSampler, build_terrain_plan, checksum
from app.game.world.genesis.terrain.address import tile_at, level_for_spacing
from app.game.world.genesis.hydro_geometry.plan import build_geometry_plan
from app.game.world.genesis.hydro_geometry.regional import boundary_probe_request
from app.game.world.genesis.hydro_geometry.spatial import between


def main():
    source, h1, _ = sources(42, 63_710_000)
    before = checksum(source.to_dict())
    sampler = TerrainSampler(build_terrain_plan(source))
    plan = build_geometry_plan(sampler.plan, h1, regional_signature(h1, RegionalHydrologyConfig()))
    g, datum = geometry(h1.config.level), source.config.sea_level_m*1000
    shoreline_edges = [(a, b) for a, b in g.edges if (h1.heights[a]*1000 >= datum) != (h1.heights[b]*1000 >= datum)][:16]
    witness = None
    for a, b in shoreline_edges:
        pa, pb = g.points[a], g.points[b]
        land = h1.heights[a]*1000 >= datum
        for _ in range(32):
            mid = between(pa, pb, 1, 2)
            raw = evaluate(source.seed, source.config, source.plates, mid, causes=False)["elevation_m"]*1000
            t1 = sampler.sample(mid)["height_mm"]
            if (raw >= datum) != (t1 >= datum):
                witness = mid
                break
            if (raw >= datum) == land:
                pa = mid
            else:
                pb = mid
        if witness:
            break
    if witness is None:
        raise RuntimeError("No real coastal mismatch in the bounded witness search; no geography was changed")
    tile = tile_at(witness, level_for_spacing(h1.radius_m, 2, 8))
    req = boundary_probe_request(plan, sampler, tile, "east", ["west"], grid_intervals=16)
    output = Path(__file__).resolve().parents[2]/"artifacts/hydro-geometry-g1/coast-seed-42"
    data, summary = emit(plan, sampler, req, output, title="seed 42 / real V4-T1 coastal disagreement")
    assert checksum(source.to_dict()) == before
    (output/"coast.json").write_text(json.dumps(data["coast"], indent=2), encoding="utf-8")
    print(json.dumps({"coastal_disagreements": summary["coastal_disagreements"], "v4_checksum_unchanged": before}))


if __name__ == "__main__":
    main()
