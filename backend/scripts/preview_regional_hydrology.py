"""Offline HR1 audit; bounded selected regions, never opens a campaign database."""
import argparse
import json
from pathlib import Path
import statistics
import time
import tracemalloc

from app.game.world.genesis.formation_plan import build_plan, indexed_cell
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.plan import build_hydrology_plan
from app.game.world.genesis.hydrology.regional import (
    RegionalHydrologyConfig, build_regional_hydrology, compare_regional_connection, regional_sector_snapshot,
)
from app.game.world.genesis.hydrology.regional_preview import write_regional_preview
from app.game.world.genesis.sphere_topology import SurfacePoint, cell_at


def selected_nodes(h1):
    seams = [i for i in sorted(h1.channel_index) if indexed_cell(i, h1.config.level).face !=
             indexed_cell(h1.drainage.parent[i], h1.config.level).face]
    incoming = {}
    for i in h1.channel_index:
        incoming[h1.drainage.parent[i]] = incoming.get(h1.drainage.parent[i], 0)+1
    confluences = sorted(n for n, count in incoming.items() if count >= 2)
    return sorted(set(seams[:3] + [h1.drainage.parent[i] for i in seams[:3]] + confluences[:2]))


def run(seed, radius, args):
    source = build_plan(seed, FormationConfigV4(radius_m=radius))
    h1 = build_hydrology_plan(source, HydrologyConfig())
    output = args.output/f"seed-{seed}-r{radius}"
    output.mkdir(parents=True, exist_ok=True)
    nodes = args.nodes if args.nodes is not None else selected_nodes(h1)
    if len(nodes) > 16:
        raise ValueError("Preview permits at most 16 explicitly selected regions per planet")
    rows, all_ports, regions = [], {}, {}
    for node in nodes:
        start = time.perf_counter()
        region = build_regional_hydrology(source, h1, node, RegionalHydrologyConfig(depth=args.depth))
        regions[node] = region
        elapsed = time.perf_counter()-start
        for port in region["ports"]:
            if port["id"] in all_ports:
                assert all_ports[port["id"]] == port
            all_ports[port["id"]] = port
        folder = output/f"node-{node}"
        write_regional_preview(source, h1, region, folder)
        (folder/"region.json").write_text(json.dumps(region, separators=(",", ":")), encoding="utf-8")
        queries = []
        for segment in region["segments"][:50]:
            p = SurfacePoint(*(a+b for a, b in zip(*segment["points"])))
            key = cell_at(p, max(h1.config.level, source.config.sector_level))
            start = time.perf_counter()
            regional_sector_snapshot(region, key)
            queries.append((time.perf_counter()-start)*1000)
        row = {"node": node, "tile": region["tile"], "build_seconds": round(elapsed, 5),
            "sample_count": region["budget"]["sample_count"], "graphs": region["budget"]["graph_count"],
            "segments": len(region["segments"]), "routes": len(region["routes"]),
            "compatible_routes": sum(r["status"] == "sampled_compatible_peer_validation_pending" for r in region["routes"]),
            "issues": region["issues"], "relocated_ports": sum(p["point"] != p["h1_representative_port"] for p in region["ports"]),
            "serialized_bytes": len(json.dumps(region, separators=(",", ":")).encode()),
            "in_memory_query_median_ms": round(statistics.median(queries), 5) if queries else None}
        if args.measure_memory and not rows:
            tracemalloc.start()
            measured = build_regional_hydrology(source, h1, node, RegionalHydrologyConfig(depth=args.depth))
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert measured == region
            row["tracemalloc_peak_bytes_excluding_v4_h1"] = peak
        rows.append(row)
        print(json.dumps({"seed": seed, "radius_m": radius, **row}), flush=True)
    connections = [compare_regional_connection(regions[p["source_node"]], regions[p["target_node"]], p["id"])
        for p in all_ports.values() if p["source_node"] in regions and p["target_node"] in regions]
    summary = {"seed": seed, "radius_m": radius, "depth": args.depth, "source_signature": source.signature,
        "h1_signature": h1.signature, "regions": rows, "shared_ports_checked": len(all_ports),
        "bilateral_connections": connections,
        "scope": "selected_regions_not_whole_planet_statistics", "actual_water_availability": "unknown"}
    (output/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="HR1 technical regional comparison, no save writes")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--radius-m", type=int, default=63_710_000)
    parser.add_argument("--depth", type=int, choices=(2, 3, 4), default=3)
    parser.add_argument("--nodes", type=int, nargs="+")
    parser.add_argument("--suite", action="store_true")
    parser.add_argument("--measure-memory", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = [(42, 63_710_000), (0, 63_710_000), (2026, 6_371_000)] if args.suite else [(args.seed, args.radius_m)]
    results = [run(seed, radius, args) for seed, radius in cases]
    (args.output/"comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
