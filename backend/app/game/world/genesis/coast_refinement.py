"""R1 subordinate, bounded baseline patches. Never relabels macro components.

Fragments identify a fixed patch sample graph, not global continents or playable
routes. Shared ports can relate adjacent patches without merging/renumbering IDs.
"""
from collections import deque

from .formation_noise import unit_direction
from .formation_plan import FormationPlan
from .formation_tectonics import evaluate
from .sphere_area import cell_solid_angle
from .sphere_topology import CellKey, DIRECTIONS, SurfacePoint, cell_at, cell_center, neighbor

MAX_DEPTH = 5
MAX_SAMPLES = 32_768
PROBES = (1, 2, 3)  # quarters of a center-to-center arc, in fixed-point ray space
SHORE_STEPS = 8


def _address(key: CellKey) -> str:
    return f"{key.face}.{key.level}.{key.x}.{key.y}"


def _between(a: SurfacePoint, b: SurfacePoint, numerator: int, denominator: int) -> SurfacePoint:
    if numerator == 0:
        return a
    if numerator == denominator:
        return b
    ua, ub = unit_direction(a), unit_direction(b)
    return SurfacePoint(*(x*(denominator-numerator)+y*numerator for x, y in zip(ua, ub)))


def build_coast_patch(plan: FormationPlan, tile: CellKey, detail_level: int) -> dict:
    if (type(detail_level) is not int or not tile.level <= detail_level <= min(24, tile.level+MAX_DEPTH)
            or tile.level < plan.config.macro_level):
        raise ValueError("Patch must refine a macro cell/descendant by at most five levels")
    factor = 2**(detail_level-tile.level)
    interior = {CellKey(tile.face, detail_level, tile.x*factor+x, tile.y*factor+y)
                for y in range(factor) for x in range(factor)}
    cells = interior | {neighbor(key, d) for key in interior for d in DIRECTIONS}
    points = {key: cell_center(key) for key in cells}
    heights = {}
    def height(point):
        if point not in heights:
            if len(heights) >= MAX_SAMPLES:
                raise ValueError("Refinement sample budget exhausted")
            heights[point] = evaluate(plan.seed, plan.config, plan.plates, point, causes=False)["elevation_m"]
        return heights[point]
    def is_land(point):
        return height(point) >= plan.config.sea_level_m
    kinds = {key: is_land(points[key]) for key in sorted(cells)}
    edges = sorted({tuple(sorted((key, other))) for key in interior for d in DIRECTIONS
                    for other in (neighbor(key, d),)})
    links = {key: [] for key in cells}
    ports, shores, obstructions = [], [], []
    for a, b in edges:
        pa, pb = points[a], points[b]
        same_kind = kinds[a] == kinds[b]
        continuous = same_kind and all(is_land(_between(pa, pb, n, 4)) == kinds[a] for n in PROBES)
        edge_id = f"coast-port-r1:{plan.signature}:{_address(a)}|{_address(b)}"
        if continuous:
            links[a].append(b)
            links[b].append(a)
        elif same_kind:
            obstructions.append(edge_id)
        else:
            # Retain a deterministic bracket of opposite signs, rather than
            # claiming a unique crossing if the arc contains several shores.
            lo, hi, denominator = 0, 2**SHORE_STEPS, 2**SHORE_STEPS
            while hi-lo > 1:
                mid = (lo+hi)//2
                if is_land(_between(pa, pb, mid, denominator)) == kinds[a]:
                    lo = mid
                else:
                    hi = mid
            left, right = _between(pa, pb, lo, denominator), _between(pa, pb, hi, denominator)
            shores.append({"edge_id": edge_id, "bracket": [list(left.xyz), list(right.xyz)],
                           "elevation_m": [height(left), height(right)]})
        if (a in interior) != (b in interior):
            ports.append({"id": edge_id, "cells": [list(vars(a).values()), list(vars(b).values())],
                          "kind_a": "land" if kinds[a] else "water", "kind_b": "land" if kinds[b] else "water",
                          "continuous_kind_at_samples": continuous})
    labels, fragments = {}, []
    tile_id = _address(tile)
    for anchor in sorted(interior):
        if anchor in labels:
            continue
        group, pending, seen = [], deque([anchor]), {anchor}
        while pending:
            key = pending.popleft()
            group.append(key)
            for other in links[key]:
                if other not in seen:
                    seen.add(other)
                    pending.append(other)
        local = sorted(interior.intersection(group))
        kind = "land" if kinds[anchor] else "water"
        identifier = f"coast-fragment-r1:{plan.signature}:{tile_id}:L{detail_level}:{kind}:{_address(local[0])}"
        for key in local:
            labels[key] = identifier
        parents = {plan.component_at(points[key]).id for key in local}
        same_kind_parents = {plan.component_at(points[key]).id for key in local
            if (plan.component_at(points[key]).kind == "landmass") == kinds[anchor]}
        fragments.append({"id": identifier, "kind": kind, "cells": [list(vars(k).values()) for k in local],
            "open": any(k not in interior for k in group), "sampled_area_m2": sum(cell_solid_angle(k) for k in local)*plan.config.radius_m**2,
            "macro_coverage_ids": sorted(parents), "same_kind_macro_ids": sorted(same_kind_parents),
            "relation": "located_in_macro_coverage_not_global_membership"})
    for port in ports:
        a, b = (CellKey(*key) for key in port["cells"])
        port["local_fragment_id"] = labels[a if a in interior else b]
    return {"refinement_version": 1, "source_generator_version": plan.config.generator_version, "plan_signature": plan.signature,
            "tile": list(vars(tile).values()), "detail_level": detail_level, "baseline_only": True,
            "guarantee": "fixed_patch_sample_graph_with_quarter_arc_probes",
            "interior_cells": len(interior), "halo_cells": len(cells)-len(interior),
            "sample_count": len(heights), "sample_budget": MAX_SAMPLES,
            "fragments": fragments, "ports": ports, "shore_brackets": shores,
            "subcell_obstructions": obstructions}


def fragment_at(patch: dict, point: SurfacePoint) -> dict:
    """Query only the canonical interior owned by this fixed patch, not a global ID."""
    if patch.get("refinement_version") != 1 or patch.get("source_generator_version") not in (3, 4):
        raise ValueError("Unsupported subordinate refinement")
    tile = CellKey(*patch["tile"])
    key = cell_at(point, patch["detail_level"])
    if key.parent(tile.level) != tile:
        raise ValueError("Point is not canonically owned by this patch")
    address = list(vars(key).values())
    for fragment in patch["fragments"]:
        if address in fragment["cells"]:
            return fragment
    raise ValueError("Incomplete subordinate patch")
