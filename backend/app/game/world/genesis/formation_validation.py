"""Bounded offline quality measurements. Never changes v3 geography or IDs."""
from array import array
from dataclasses import dataclass
from functools import lru_cache
import math
import time

from .formation_plan import FormationPlan, indexed_cell
from .formation_tectonics import evaluate
from .formation_config import calibrated_scale
from .sphere_area import cell_solid_angle, rectangle_solid_angle
from .sphere_topology import BASES, DIRECTIONS, SurfacePoint, cell_center, neighbor, owning_face


@lru_cache(maxsize=2)
def grid_geometry(level: int) -> tuple:
    if type(level) is not int or not 2 <= level <= 7:
        raise ValueError("Diagnostic level must be 2..7 (at most 98,304 samples)")
    count = 6*4**level
    n = 2**level
    keys = [indexed_cell(i, level) for i in range(count)]
    points = tuple(cell_center(k) for k in keys)
    weights = tuple(cell_solid_angle(k) for k in keys)
    adjacency = tuple(tuple((other.face*n*n+other.y*n+other.x)
                     for other in (neighbor(k, d) for d in DIRECTIONS)) for k in keys)
    return points, weights, adjacency


def component_labels(mask, adjacency) -> tuple[tuple[int, ...], list[list[int]]]:
    """Canonical complete sample-grid components, not replacement physical IDs."""
    if len(mask) != len(adjacency):
        raise ValueError("Mask and adjacency sizes differ")
    labels, groups = [-1]*len(mask), []
    for anchor in range(len(mask)):
        if labels[anchor] >= 0:
            continue
        label, pending, members = len(groups), [anchor], []
        labels[anchor] = label
        while pending:
            index = pending.pop()
            members.append(index)
            for other in adjacency[index]:
                if labels[other] < 0 and mask[index] == mask[other]:
                    labels[other] = label
                    pending.append(other)
        groups.append(members)
    return tuple(labels), groups


def _angle(a, b):
    x, y, z = a.xyz
    u, v, w = b.xyz
    return math.atan2(math.hypot(y*w-z*v, z*u-x*w, x*v-y*u), x*u+y*v+z*w)


def weighted_quantile(values, weights, quantile: float) -> int:
    if not values or len(values) != len(weights) or not 0 <= quantile <= 1:
        raise ValueError("Invalid weighted distribution")
    target = math.fsum(weights)*quantile
    cumulative = 0.0
    for value, weight in sorted(zip(values, weights)):
        cumulative += weight
        if cumulative >= target:
            return value
    return max(values)


def plate_site_density(plans) -> dict:
    """Measure known v3 site placement anisotropy; does not change nucleation."""
    area = {"center": 6*rectangle_solid_angle(-.5, -.5, .5, .5)/(4*math.pi),
            "corner": 24*rectangle_solid_angle(.5, .5, 1, 1)/(4*math.pi)}
    area["edge"] = 1-sum(area.values())
    counts = {zone: 0 for zone in area}
    for plan in plans:
        for plate in plan.plates:
            point = SurfacePoint(*plate.center)
            normal, u, v = BASES[owning_face(point)]
            dot = lambda axis: sum(a*b for a, b in zip(point.xyz, axis))
            cu, cv = abs(dot(u)/dot(normal)), abs(dot(v)/dot(normal))
            zone = "center" if max(cu, cv) < .5 else "corner" if min(cu, cv) >= .5 else "edge"
            counts[zone] += 1
    count = sum(counts.values())
    if not count:
        raise ValueError("At least one plate inventory is required")
    return {"sphere_area_fraction": area, "sampled_plate_sites": counts,
            "site_fraction": {k: v/count for k, v in counts.items()},
            "site_density_relative_to_surface_average": {k: v/count/area[k] for k, v in counts.items()},
            "meaning": "site-density anisotropy; not a terrain seam or proof of degenerate geography"}


@dataclass
class DiagnosticGrid:
    level: int
    heights: array
    tectonic: array
    labels: tuple[int, ...]
    macro_mismatch: bytearray
    summary: dict


def measure_plan(plan: FormationPlan, level: int = 6) -> DiagnosticGrid:
    started = time.perf_counter()
    points, weights, adjacency = grid_geometry(level)
    heights, tectonic = array("i"), array("i")
    macro_mismatch = bytearray()
    mismatch_weight, macro_land_weight = 0.0, 0.0
    for point, weight in zip(points, weights):
        sample = evaluate(plan.seed, plan.config, plan.plates, point, causes=False)
        height = sample["elevation_m"]
        heights.append(height)
        tectonic.append(sample["terms_m"]["tectonic"])
        local_land = height >= plan.config.sea_level_m
        macro_land = plan.component_at(point).kind == "landmass"
        mismatch_weight += weight*(local_land != macro_land)
        macro_mismatch.append(local_land != macro_land)
        macro_land_weight += weight*macro_land
    sampled_seconds = time.perf_counter()-started
    land = [z >= plan.config.sea_level_m for z in heights]
    labels, groups = component_labels(land, adjacency)
    total = math.fsum(weights)
    land_weight = math.fsum(w for w, is_land in zip(weights, land) if is_land)
    bodies = []
    for members in groups:
        first = members[0]
        farthest = max(members, key=lambda i: _angle(points[first], points[i]))
        extent = max(_angle(points[farthest], points[i]) for i in members)*plan.config.radius_m
        bodies.append({"kind": "land" if land[first] else "water", "anchor_index": first,
            "sample_cells": len(members), "sphere_area_fraction": math.fsum(weights[i] for i in members)/total,
            "extent_lower_bound_km": extent/1000})
    land_bodies = [b for b in bodies if b["kind"] == "land"]
    water_bodies = [b for b in bodies if b["kind"] == "water"]
    ridge = [is_land and t >= 1000 for is_land, t in zip(land, tectonic)]
    _, ridge_groups = component_labels(ridge, adjacency)
    ridge_groups = [g for g in ridge_groups if ridge[g[0]]]
    ridge_extents = []
    for members in ridge_groups:
        first = members[0]
        farthest = max(members, key=lambda i: _angle(points[first], points[i]))
        ridge_extents.append(max(_angle(points[farthest], points[i]) for i in members)*plan.config.radius_m/1000)
    transitions = sum(land[i] != land[j] for i, adjacent in enumerate(adjacency) for j in adjacent if i < j)
    mean = math.fsum(z*w for z, w in zip(heights, weights))/total
    summary = {"seed": plan.seed, "radius_m": plan.config.radius_m, "plan_signature": plan.signature,
        "audit_version": 1, "config": plan.config.model_dump(mode="json"), "scale": calibrated_scale(plan.config),
        "diagnostic_level": level, "sample_count": len(heights), "solid_angle_sum": total,
        "weighted_land_fraction": land_weight/total, "weighted_water_fraction": 1-land_weight/total,
        "unweighted_land_fraction": sum(land)/len(land), "weighted_macro_land_fraction": macro_land_weight/total,
        "weighted_macro_disagreement_fraction": mismatch_weight/total,
        "land_components": len(land_bodies), "water_components": len(water_bodies),
        "macro_land_components": sum(c.kind == "landmass" for c in plan.components),
        "macro_water_components": sum(c.kind == "water_body" for c in plan.components),
        "largest_land_share_of_land": max((b["sphere_area_fraction"] for b in land_bodies), default=0)/(land_weight/total) if land_weight else 0,
        "largest_water_share_of_water": max((b["sphere_area_fraction"] for b in water_bodies), default=0)/(1-land_weight/total) if land_weight < total else 0,
        "small_land_components_le_4_cells": sum(b["sample_cells"] <= 4 for b in land_bodies),
        "longest_land_extent_lower_bound_km": max((b["extent_lower_bound_km"] for b in land_bodies), default=0),
        "longest_uplift_belt_lower_bound_km": max(ridge_extents, default=0),
        "uplift_belt_components": len(ridge_groups), "shore_sample_edges": transitions,
        "elevation_m": {"min": min(heights), "max": max(heights), "mean": mean,
            "stddev": math.sqrt(math.fsum((z-mean)**2*w for z, w in zip(heights, weights))/total),
            **{f"p{int(q*100):02d}": weighted_quantile(heights, weights, q) for q in (.05, .25, .5, .75, .95)}},
        "largest_bodies": sorted(bodies, key=lambda b: b["sphere_area_fraction"], reverse=True)[:12],
        "plate_count": len(plan.plates), "sampling_seconds": sampled_seconds,
        "analysis_seconds": time.perf_counter()-started-sampled_seconds,
        "flags": (["no_sampled_land"] if not land_bodies else [])+(["no_sampled_water"] if not water_bodies else [])}
    return DiagnosticGrid(level, heights, tectonic, labels, macro_mismatch, summary)
