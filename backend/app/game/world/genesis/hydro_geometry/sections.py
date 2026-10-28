"""Sampled geometric section areas; no discharge law or actual river dimensions."""
from fractions import Fraction
from math import isqrt
from ..sphere_topology import SurfacePoint
from .spatial import UNIT, direction


def section_curve(heights, step_mm):
    middle = len(heights)//2
    bottom = heights[middle]
    escape = min(max(heights[:middle]), max(heights[middle+1:]))
    candidates = sorted({z for z in heights if bottom < z < escape} | ({escape-1} if escape > bottom+1 else set()))
    # At most eight topographically derived stages, not chosen water levels.
    candidates = sorted({candidates[i*len(candidates)//min(8, len(candidates))] for i in range(min(8, len(candidates)))}) if candidates else []
    curve = []
    for level in candidates:
        area, width = Fraction(0), Fraction(0)
        closed = True
        for sign in (-1, 1):
            i = middle
            while 0 <= i+sign < len(heights):
                a, b = heights[i], heights[i+sign]
                if b >= level:
                    extent = Fraction((level-a)*step_mm, b-a) if b > a else Fraction(0)
                    area += (level-a)*extent/2
                    width += extent
                    break
                area += Fraction((2*level-a-b)*step_mm, 2)
                width += step_mm
                i += sign
            else:
                closed = False
        if closed:
            curve.append({"stage_mm": level, "connected_width_mm": int(width),
                          "max_depth_at_axis_mm": level-bottom, "cross_section_area_mm2": int(area)})
    return {"axis_height_mm": bottom, "sampled_lateral_escape_height_mm": escape if escape > bottom else None,
            "status": "sampled_banked_section" if curve else "no_enclosed_section_demonstrated",
            "stage_geometry": curve, "actual_width_mm": None, "actual_depth_mm": None,
            "discharge_capacity_m3_s": None, "method": "piecewise_linear_connected_section_not_hydraulic_capacity"}


def sample_section(context, point, downstream, radius, config):
    if config.section_step_m*config.section_half_intervals*100 > radius:
        return None  # Tangent-distance approximation is not supported at this scale.
    a, b = direction(point), direction(downstream)
    tangent = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    length = isqrt(sum(v*v for v in tangent))
    if not length:
        return None
    tangent = tuple(v*UNIT//length for v in tangent)
    points = [point if i == 0 else SurfacePoint(*(v+t*i*config.section_step_m//radius for v, t in zip(a, tangent)))
              for i in range(-config.section_half_intervals, config.section_half_intervals+1)]
    zs = [context.height(p) for p in points]
    return {"point": list(point.xyz), "transverse_points": [list(p.xyz) for p in points],
            "terrain_profile_mm": zs, "probe_step_mm": config.section_step_m*1000,
            **section_curve(zs, config.section_step_m*1000)}
