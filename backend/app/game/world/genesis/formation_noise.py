"""Version-3 integer spherical directions and continuous ambient 3D fields."""
from math import isqrt
from functools import lru_cache

from .randomness import coordinate_seed
from .sphere_topology import SurfacePoint

UNIT = 2**30


@lru_cache(maxsize=8192)
def _node_value(seed: int, domain: str, x: int, y: int, z: int) -> int:
    """Bounded transparent memoization; the v3 hash/value formula is unchanged."""
    return coordinate_seed(seed, 3, domain, x, y, z)%20_001-10_000


def unit_direction(point: SurfacePoint) -> tuple[int, int, int]:
    norm = isqrt(sum(v*v for v in point.xyz)*UNIT**2)
    return tuple(v*UNIT**2//norm for v in point.xyz)


def dot(a, b) -> int:
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def cross(a, b) -> tuple[int, int, int]:
    return a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]


def noise(seed: int, direction: tuple[int, int, int], radius_m: int, wavelength_m: int, domain: str) -> int:
    axes = [divmod(v*radius_m//wavelength_m, UNIT) for v in direction]
    def node(x, y, z):
        return _node_value(seed, domain, axes[0][0]+x, axes[1][0]+y, axes[2][0]+z)
    def blend(a, b, t):
        return a+(b-a)*t*t*(3*UNIT-2*t)//UNIT**3
    yz = [[blend(node(0, y, z), node(1, y, z), axes[0][1]) for y in range(2)] for z in range(2)]
    zs = [blend(row[0], row[1], axes[1][1]) for row in yz]
    return blend(*zs, axes[2][1])
