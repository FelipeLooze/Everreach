"""V2 global integer 3D macro field, without per-face random streams."""
from math import isqrt

from .randomness import coordinate_seed
from .sphere_config import SphereConfig
from .sphere_topology import CellKey, SurfacePoint, face_point

UNIT = 2**40


def elevation_at(seed: int, config: SphereConfig, point: SurfacePoint) -> int:
    norm = isqrt(sum(v*v for v in point.xyz) * UNIT**2)
    axes = [divmod(((v*UNIT**2 // norm)+UNIT) * 2**config.macro_level, UNIT)
            for v in point.xyz]

    def blend(a, b, offset):
        return a + (b-a)*offset*offset*(3*UNIT-2*offset)//UNIT**3

    def node(dx, dy, dz):
        return coordinate_seed(seed, 2, "sphere_macro_elevation",
                               axes[0][0]+dx, axes[1][0]+dy, axes[2][0]+dz) % 12_001 - 6_000

    yz = [[blend(node(0, y, z), node(1, y, z), axes[0][1]) for y in range(2)] for z in range(2)]
    z_values = [blend(row[0], row[1], axes[1][1]) for row in yz]
    return blend(*z_values, axes[2][1])


def global_plan(seed: int, config: SphereConfig) -> dict:
    return {"kind": "implicit_spherical_macro_v2", "seed": seed,
            "config": config.model_dump(mode="json")}


def generate_sector(seed: int, config: SphereConfig, key: CellKey) -> dict:
    if key.level != config.sector_level:
        raise ValueError("Materialization requires the world's pinned sector level")
    intervals = config.sample_intervals
    heights = [[elevation_at(seed, config, face_point(key.face, key.x*intervals+x,
                key.y*intervals+y, 2**key.level*intervals)) for x in range(intervals+1)]
                for y in range(intervals+1)]
    return {"generator_version": 2, "cell": [key.face, key.level, key.x, key.y],
            "sample_intervals": intervals, "elevation_m": heights,
            "sea_level_m": config.sea_level_m}
