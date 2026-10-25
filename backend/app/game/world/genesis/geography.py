"""Integer, continuous macro elevation field shared by all sector boundaries.

This is a coarse land/ocean foundation, not tectonics, drainage or climate.
No continent count is chosen and no world-sized array is allocated.
"""

from .config import WorldConfig
from .coordinates import SectorKey, canonical_point, canonical_sector
from .randomness import coordinate_seed


def _blend(a: int, b: int, offset: int, span: int) -> int:
    # Cubic smoothstep, evaluated with integer arithmetic for replay stability.
    weight = offset * offset * (3 * span - 2 * offset)
    return a + (b - a) * weight // (span ** 3)


def elevation_at(seed: int, config: WorldConfig, x_m: int, y_m: int) -> int:
    x, y = canonical_point(config, x_m, y_m)
    span = config.macro_cell_m
    ix, ox = divmod(x, span)
    iy, oy = divmod(y, span)
    columns = config.width_m // span

    def node(nx: int, ny: int) -> int:
        return coordinate_seed(seed, config.generator_version, "macro_elevation",
                               nx % columns, ny) % 12_001 - 6_000

    south = _blend(node(ix, iy), node(ix + 1, iy), ox, span)
    north = _blend(node(ix, iy + 1), node(ix + 1, iy + 1), ox, span)
    return _blend(south, north, oy, span)


def global_plan(seed: int, config: WorldConfig) -> dict:
    """Compact executable global plan: its implicit lattice is evaluated on demand."""
    return {"kind": "implicit_macro_elevation_v1", "seed": seed,
            "config": config.model_dump(mode="json")}


def generate_sector(seed: int, config: WorldConfig, key: SectorKey) -> dict:
    key = canonical_sector(config, key)
    intervals = config.sector_m // config.sample_step_m
    x0, y0 = key.x * config.sector_m, key.y * config.sector_m
    heights = [[elevation_at(seed, config, x0 + x * config.sample_step_m,
                            y0 + y * config.sample_step_m)
                for x in range(intervals + 1)] for y in range(intervals + 1)]
    return {"generator_version": config.generator_version, "sector": [key.x, key.y],
            "origin_m": [x0, y0], "sample_step_m": config.sample_step_m,
            "sea_level_m": config.sea_level_m, "elevation_m": heights}
