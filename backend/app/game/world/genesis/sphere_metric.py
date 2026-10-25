"""Spherical metric; floating operations are not used for terrain generation."""
import math

from .sphere_config import SphereConfig
from .sphere_topology import SurfacePoint

QUANTIZATION = 10**15


def _unit(point: SurfacePoint) -> tuple[float, float, float]:
    length = math.hypot(*point.xyz)
    return tuple(v / length for v in point.xyz)


def _quantize(values) -> SurfacePoint:
    return SurfacePoint(*(round(v * QUANTIZATION) for v in values))


def from_lat_lon(latitude_deg: float, longitude_deg: float) -> SurfacePoint:
    if not (math.isfinite(latitude_deg) and math.isfinite(longitude_deg)) or not -90 <= latitude_deg <= 90:
        raise ValueError("Invalid latitude or longitude")
    if abs(latitude_deg) == 90:
        return SurfacePoint(0, 0, 1 if latitude_deg > 0 else -1)
    lat, lon = math.radians(latitude_deg), math.radians(longitude_deg % 360)
    return _quantize((math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat)))


def distance_m(config: SphereConfig, start: SurfacePoint, end: SurfacePoint) -> float:
    # Integer dot/cross preserve tiny angular separations and exact antipodes.
    a, b = start.xyz, end.xyz
    cross = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    dot = sum(x*y for x, y in zip(a, b))
    return config.radius_m * math.atan2(math.hypot(*cross), dot)


def advance(config: SphereConfig, start: SurfacePoint, bearing_deg: float, metres: float) -> SurfacePoint:
    """Bearing clockwise from local north; at poles east is +Y by convention.

    Quantization error per point is bounded by 2e-15*radius metres.
    """
    if not math.isfinite(bearing_deg) or not math.isfinite(metres) or metres < 0:
        raise ValueError("Invalid geodesic displacement")
    if metres == 0:
        return start
    x, y, z = _unit(start)
    horizontal = math.hypot(x, y)
    east = (-y/horizontal, x/horizontal, 0.0) if horizontal else (0.0, 1.0, 0.0)
    north = (y*east[2]-z*east[1], z*east[0]-x*east[2], x*east[1]-y*east[0])
    bearing = math.radians(bearing_deg % 360)
    angle = (metres / config.radius_m) % math.tau
    direction = tuple(n*math.cos(bearing)+e*math.sin(bearing) for n, e in zip(north, east))
    return _quantize(tuple(p*math.cos(angle)+t*math.sin(angle)
                           for p, t in zip((x, y, z), direction)))
