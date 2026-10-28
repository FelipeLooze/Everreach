"""Bounded real T1 natural-channel search; never changes height or seed."""
from fractions import Fraction
from .. import sources
from ...terrain.address import TerrainTile, tile_at
from ...terrain.field import checksum
from ...sphere_topology import SurfacePoint
from ...hydrology.geometry import geometry
from ...hydro_geometry.graph import SampleContext, BudgetExhausted
from ...hydro_geometry.spatial import between, coverage_boxes, probe_arc_upper_mm
from .allocation import surface_quota, parcel_level
from .hydraulics import transverse, capacity
from .interface import interface_contract


def inspect_parcel(water, sampler, tile, config):
    quota = surface_quota(water, tile, config)
    n = config.grid_intervals
    context = SampleContext(sampler, config.max_samples)
    points = [tile.point(x, y, n) for y in range(n+1) for x in range(n+1)]
    zs = [context.height(p) for p in points]
    if min(zs) <= water.hydrology.sea_level_m*1000:
        return None, {"status": "coastal_or_submerged_geometry_pending", "sample_count": len(context.samples)}
    edges = []
    # Internal finite-volume cells only; boundary crossing requires its own proof.
    for y in range(2, n-2):
        for x in range(2, n-2):
            a = y*(n+1)+x
            for b in (a+1, a+n+1):
                source, target = (a, b) if zs[a] > zs[b] else (b, a)
                if zs[source] > zs[target]:
                    edges.append((-(zs[source]-zs[target]), source, target))
    tested = 0
    for _, a, b in sorted(edges):
        if tested >= config.max_candidate_edges:
            break
        tested += 1
        try:
            probes = [between(points[a], points[b], i) for i in range(5)]
            heights = [context.height(p) for p in probes]
            if any(v > u for u, v in zip(heights, heights[1:])):
                continue
            sections = [transverse(context, p, probes[min(i+1, 4)] if i < 4 else probes[3], water.hydrology.radius_m, config)
                        for i, p in enumerate(probes)]
            if any(s is None for s in sections):
                continue
            areas, amounts = quota["vertex_areas_mm2"], quota["vertex_quota_liters"]
            initial_depth = amounts[a]*10**6//max(1, areas[a])
            depth = min(initial_depth//2, min(s["bank_room_mm"]-1 for s in sections))
            if depth < 2:
                continue
            estimate = capacity(sections, probes, heights, depth, heights[0]-heights[-1], {"radius_m": water.hydrology.radius_m, "policy": config})
            if estimate is None:
                continue
            reserve = (depth*areas[a]+10**6-1)//10**6
            destination_room = max(0, areas[b]*(sections[-1]["bank_room_mm"]-1)//10**6-amounts[b])
            available = min(max(0, amounts[a]-estimate["required_wetting_liters"]-reserve), destination_room)
            if available <= 0:
                continue
            destination_depth = ((amounts[b]+available)*10**6+areas[b]-1)//max(1, areas[b])
            heads = [z+depth for z in heights]
            heads[-1] = heights[-1]+destination_depth
            if any(u < v for u, v in zip(heads, heads[1:])):
                continue
            estimate = capacity(sections, probes, heights, depth, heads[0]-heads[-1], {"radius_m": water.hydrology.radius_m, "policy": config})
            deliverable = min(available, max(0, estimate["episode_capacity_liters"]-estimate["required_wetting_liters"]) if estimate else 0)
            if deliverable <= 0:
                continue
            result = {"kind": "natural_passage_k1", "practical_version": 1, "capacity_version": 1,
                "terrain_signature": sampler.plan.signature, "w1_signature": water.signature,
                "config": config.model_dump(), "allocation": quota, "source_vertex": a, "target_vertex": b,
                "points": [list(p.xyz) for p in probes], "terrain_profile_mm": heights,
                "head_profile_reference_mm": heads, "cross_sections": sections, "capacity": estimate,
                "source_reserve_liters": reserve, "destination_room_liters": destination_room,
                "suggested_transfer_liters": deliverable, "terrain_modified": False, "perennial": None,
                "scope": "one_internal_natural_passage_not_an_entire_H1_or_HR1_river",
                "terrain_coverage": coverage_boxes(points+[SurfacePoint(*ray) for section in sections for ray in section["points"]])}
            shared = tile.point(a%(n+1)+b%(n+1), a//(n+1)+b//(n+1), n*2)
            shared_height = context.height(shared)
            shared_head = shared_height+depth
            if not heads[0] >= shared_head >= heads[-1]:
                continue
            result["shared_interface"] = interface_contract(sampler.plan.signature,
                [list(points[a].xyz), list(points[b].xyz)], list(shared.xyz), shared_height, shared_head)
            result["proof_id"] = checksum(result)[:32]
            return result, {"status": "natural_passage_found", "tested_edges": tested, "sample_count": len(context.samples)}
        except BudgetExhausted:
            return None, {"status": "pending_sample_budget", "tested_edges": tested, "sample_count": len(context.samples)}
    return None, {"status": "no_passage_demonstrated_in_bounded_search", "tested_edges": tested, "sample_count": len(context.samples)}


def select_candidates(water, sampler, config):
    from ...sphere_topology import SurfacePoint
    h1 = water.hydrology
    surface = water.solution.periods[-1]["stores"]["surface"]
    annual = [sum(p["fluxes"]["local_runoff"][i] for p in water.solution.periods) for i in range(len(h1.heights))]
    eligible = [i for i in range(len(h1.heights)) if surface[i] and annual[i] and h1.heights[i] >= h1.sea_level_m]
    eligible.sort(key=lambda i: (-Fraction(surface[i], h1.cell_area_m2[i]), -Fraction(annual[i], h1.cell_area_m2[i]), i))
    trials = []
    for node in eligible[:config.max_macro_candidates]:
        tile = tile_at(geometry(h1.config.level).points[node], parcel_level(h1.radius_m, config))
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (0, -1), (-1, -1), (1, -1))[:config.max_tiles_per_macro]:
            if not 0 <= tile.x+dx < 2**tile.level or not 0 <= tile.y+dy < 2**tile.level:
                continue
            candidate = TerrainTile(tile.face, tile.level, tile.x+dx, tile.y+dy)
            found, summary = inspect_parcel(water, sampler, candidate, config)
            trials.append({"node": node, "tile": list(vars(candidate).values()), **summary})
            if found:
                return found, trials
    return None, trials
