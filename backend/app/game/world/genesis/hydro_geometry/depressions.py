"""Bounded sampled depressions and potential capacity, never lake occupancy."""
from .graph import flood, directed


def investigate(graph, radius, expansion_budget, evidence_id):
    costs, parent, rank, complete = flood(graph, graph.boundary, expansion_budget, radius)
    if not complete:
        return {"status": "pending_budget", "depressions": [], "expansions": len(rank)}
    raised = {i for i in rank if costs[i][0] > graph.heights[i]}
    groups, seen = [], set()
    for anchor in sorted(raised):
        if anchor in seen:
            continue
        level = costs[anchor][0]
        group, queue = [], [anchor]
        seen.add(anchor)
        while queue:
            a = queue.pop()
            group.append(a)
            for b in graph.adjacent[a]:
                if b in raised and b not in seen and costs[b][0] == level and max(directed(graph, a, b)[1]) < level:
                    seen.add(b)
                    queue.append(b)
        members = set(group)
        escapes = sorted((a, b) for a in group for b in graph.adjacent[a] if b not in members
                         and max(max(directed(graph, a, b)[1]), costs[b][0]) == level)
        stages = sorted({graph.heights[a] for a in group if graph.heights[a] < level} | {level})
        if len(stages) > 8:
            stages = sorted({stages[i*(len(stages)-1)//7] for i in range(8)})
        curve = [{"stage_mm": z, "potential_storage_liters": sum(graph.areas_mm2[a]*max(0, z-graph.heights[a]) for a in group)//10**6}
                 for z in stages]
        for item in curve:
            wet = {v for v in group if graph.heights[v] < item["stage_mm"]}
            count = 0
            while wet:
                count += 1
                pending = [min(wet)]
                wet.remove(pending[0])
                while pending:
                    a = pending.pop()
                    linked = [b for b in graph.adjacent[a] if b in wet and max(directed(graph, a, b)[1]) < item["stage_mm"]]
                    wet.difference_update(linked)
                    pending.extend(linked)
            item["sampled_wet_component_count"] = count
        contours = []
        for a in sorted(group):
            for b in graph.adjacent[a]:
                if b in members:
                    continue
                ps, zs = directed(graph, a, b)
                for pa, pb, za, zb in zip(ps, ps[1:], zs, zs[1:]):
                    if min(za, zb) <= level-1 < max(za, zb):
                        contours.append({"inside_vertex": a, "other_vertex": b,
                            "stage_mm": level-1, "crossing_bracket": [list(pa.xyz), list(pb.xyz)],
                            "terrain_bracket_mm": [za, zb]})
        groups.append({"id": f"g1-depression:{evidence_id}:{anchor}", "vertices": sorted(group),
            "bottom_height_mm": min(graph.heights[a] for a in group), "spill_height_mm": level,
            "spill_edges": [[a, b] for a, b in escapes], "potential_hypsometry": curve,
            "contour_crossing_brackets": contours, "contour_closed_polygon_validated": False,
            "footprint_vertices": [list(graph.points[a].xyz) for a in sorted(group)],
            "status": "sampled_closed_below_spill" if escapes else "outlet_geometry_pending",
            "capacity_method": "integer_midpoint_spherical_dual_columns_not_exact_bathymetry",
            "capacity_semantics": "union_of_sampled_columns_stage_connectivity_may_have_multiple_components",
            "water_volume_liters": None, "flooded_area_m2": None, "permanent": None})
    return {"status": "sampled_domain_only", "depressions": groups, "expansions": len(rank),
            "outside_domain_connectivity": "unresolved", "subgrid_geometry": "unresolved"}
