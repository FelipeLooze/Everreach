"""Exact shared corridor ports, not final river beds or actual wet features."""
from fractions import Fraction
from math import lcm
import hashlib

from ..formation_plan import cell_index, indexed_cell
from ..sphere_topology import BASES, CellKey, SurfacePoint, cell_at
from .geometry import geometry
from .plan import HydrologyPlan


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _face_uv(point: SurfacePoint, face: int):
    normal, axis_u, axis_v = BASES[face]
    scale = _dot(point.xyz, normal)
    if scale <= 0:
        raise ValueError("Corridor point is behind its cube chart")
    return Fraction(_dot(point.xyz, axis_u), scale), Fraction(_dot(point.xyz, axis_v), scale)


def _ray(face: int, u: Fraction, v: Fraction) -> SurfacePoint:
    denominator = lcm(u.denominator, v.denominator)
    normal, axis_u, axis_v = BASES[face]
    return SurfacePoint(*(normal[i]*denominator + axis_u[i]*u.numerator*(denominator//u.denominator)
                          + axis_v[i]*v.numerator*(denominator//v.denominator) for i in range(3)))


def clip_segment(start: SurfacePoint, end: SurfacePoint, key: CellKey):
    """Liang-Barsky in rational gnomonic coordinates; no seam rounding."""
    a, b = _face_uv(start, key.face), _face_uv(end, key.face)
    n = 2**key.level
    lower = (Fraction(2*key.x, n)-1, Fraction(2*key.y, n)-1)
    upper = (Fraction(2*(key.x+1), n)-1, Fraction(2*(key.y+1), n)-1)
    enter, leave = Fraction(0), Fraction(1)
    for axis in range(2):
        delta = b[axis]-a[axis]
        if delta == 0:
            if not lower[axis] <= a[axis] <= upper[axis]:
                return None
            continue
        first, second = (lower[axis]-a[axis])/delta, (upper[axis]-a[axis])/delta
        enter, leave = max(enter, min(first, second)), min(leave, max(first, second))
        if enter >= leave:
            return None
    left = _ray(key.face, *(a[i]+(b[i]-a[i])*enter for i in range(2)))
    right = _ray(key.face, *(a[i]+(b[i]-a[i])*leave for i in range(2)))
    return (left, right) if left != right else None


def corridor_port_id(plan: HydrologyPlan, edge_index: int, point: SurfacePoint) -> str:
    g = geometry(plan.config.level)
    for node in g.edges[edge_index]:
        if point == g.points[node]:
            return plan.identifier("junction", node)
    value = f"{edge_index}:{point.x}:{point.y}:{point.z}"
    digest = hashlib.sha256(value.encode()).hexdigest()[:24]
    return f"hydro-port-h1:{plan.signature}:{digest}"


def port_condition(plan: HydrologyPlan, edge_index: int, point: SurfacePoint) -> dict:
    g = geometry(plan.config.level)
    nodes = g.edges[edge_index]
    for node in nodes:
        if point == g.points[node]:
            return {"kind": "exact_macro_potential_head", "head_m": plan.drainage.head[node]}
    values = [plan.drainage.head[n] for n in nodes]
    return {"kind": "macro_head_bounds_pending_refinement", "minimum_m": min(values), "maximum_m": max(values)}


def query_point(plan: HydrologyPlan, point: SurfacePoint) -> dict:
    node = cell_index(cell_at(point, plan.config.level))
    d = plan.drainage
    basin = None if d.marine[node] and d.area[node] == 0 else plan.identifier("basin", d.outlet[node])
    return {"macro_node": node, "basin_id": basin,
            "unconditioned_terminal_id": plan.identifier("raw-terminal", d.raw_outlet[node]),
            "closed_unconditioned_basin_candidate": not d.marine[d.raw_outlet[node]],
            "macro_center_terrain_m": plan.heights[node], "macro_center_potential_head_m": d.head[node],
            "contributing_area_m2": d.area[node], "potential_strahler_order": d.order[node],
            "connected_to_reference_ocean_at_samples": d.marine[node],
            "geometry_status": "macro_potential_requires_regional_refinement", "actual_wet_state": None}


def sector_snapshot(plan: HydrologyPlan, key: CellKey) -> dict:
    g, level = geometry(plan.config.level), plan.config.level
    if key.level >= level:
        covered = (cell_index(key.parent(level)),)
    else:
        factor = 2**(level-key.level)
        covered = tuple(cell_index(CellKey(key.face, level, key.x*factor+x, key.y*factor+y))
                        for y in range(factor) for x in range(factor))
    candidates = set()
    d = plan.drainage
    for node in covered:
        if node in plan.channel_index:
            candidates.add(node)
        candidates.update(other for other, _ in g.adjacency[node]
                          if other in plan.channel_index and d.parent[other] == node)
    corridors = []
    for source in sorted(candidates):
        target = d.parent[source]
        index = g.edge_lookup[tuple(sorted((source, target)))]
        port = g.ports[index]
        parts = ((g.points[source], port, indexed_cell(source, level).face),
                 (port, g.points[target], indexed_cell(target, level).face))
        clipped = []
        for a, b, face in parts:
            if face != key.face:
                continue
            result = clip_segment(a, b, key)
            if result:
                if clipped and clipped[-1][-1] == result[0]:
                    clipped[-1].append(result[1])
                else:
                    clipped.append(list(result))
        for points in clipped:
            reach = plan.reaches[plan.channel_index[source]]
            corridors.append({"edge_id": plan.identifier("edge", index),
                "reach_id": plan.identifier("reach", reach.start), "source_node": source, "target_node": target,
                "points": [list(p.xyz) for p in points],
                "entry_port_id": corridor_port_id(plan, index, points[0]),
                "exit_port_id": corridor_port_id(plan, index, points[-1]),
                "entry_head_condition": port_condition(plan, index, points[0]),
                "exit_head_condition": port_condition(plan, index, points[-1]),
                "hydraulic_head_bounds_m": [d.head[target], d.head[source]],
                "contributing_area_m2": d.area[source], "water_availability": "unknown",
                "requires_regional_refinement": True, "river_bed_geometry_final": False})
    center = _ray(key.face, Fraction(2*key.x+1, 2**key.level)-1,
                  Fraction(2*key.y+1, 2**key.level)-1)
    return {"hydrology_version": 1, "hydrology_signature": plan.signature,
            "source_signature": plan.source_signature, "sector": [key.face, key.level, key.x, key.y],
            "baseline_only": True, "classification": query_point(plan, center), "corridors": corridors,
            "actually_fed_watercourses": [], "water_balance": "not_modeled"}
