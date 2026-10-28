"""Local finite-difference geometry from the same T1 authority, never a new field."""
from math import isqrt
from ..sphere_topology import SurfacePoint
from .field import PRECISION, _direction


def surface_geometry(sampler, point, probe_m=8):
    if type(probe_m) is not int or not 1 <= probe_m <= 1000:
        raise ValueError("Geometry probe must be 1..1000 physical metres")
    d = _direction(point)
    i = min(range(3), key=lambda k: abs(d[k]))
    ref = tuple(PRECISION if k == i else 0 for k in range(3))
    def cross(a, b):
        return a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]
    def normalize(v):
        length = isqrt(sum(a*a for a in v))
        return tuple(a*PRECISION//length for a in v)
    axes = normalize(cross(d, ref)), normalize(cross(d, normalize(cross(d, ref))))
    radius = sampler.plan.source.config.radius_m
    slopes = []
    for axis in axes:
        points = [SurfacePoint(*((v+sign*t*probe_m//radius)//2**14 for v, t in zip(d, axis))) for sign in (-1, 1)]
        heights = [sampler.sample(p)["height_mm"] for p in points]
        slopes.append((heights[1]-heights[0])*1000//(2*probe_m))
    return {**sampler.sample(point), "gradient_tangent_ppm": slopes,
            "slope_magnitude_ppm": isqrt(sum(s*s for s in slopes)), "probe_m": probe_m,
            "geometry_method": "symmetric_tangent_probes_approximate_arc_distance",
            "terrain_baseline_only": True, "terrain_modifications_applied": False,
            "material_assignment": None, "river_bed_validated": False}
