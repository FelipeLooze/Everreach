from dataclasses import dataclass

from .config import WorldConfig


@dataclass(frozen=True, order=True)
class SectorKey:
    x: int
    y: int


def canonical_point(config: WorldConfig, x_m: int, y_m: int) -> tuple[int, int]:
    if type(x_m) is not int or type(y_m) is not int:
        raise ValueError("Coordinates must be integer atlas metres")
    if not 0 <= y_m <= config.height_m:
        raise ValueError("Point lies outside the finite atlas")
    return x_m % config.width_m, y_m


def canonical_sector(config: WorldConfig, key: SectorKey) -> SectorKey:
    if type(key.x) is not int or type(key.y) is not int:
        raise ValueError("Sector indices must be integers")
    if not 0 <= key.y < config.height_m // config.sector_m:
        raise ValueError("Sector lies outside the finite atlas")
    return SectorKey(key.x % (config.width_m // config.sector_m), key.y)


def sector_at(config: WorldConfig, x_m: int, y_m: int) -> SectorKey:
    x, y = canonical_point(config, x_m, y_m)
    # The north endpoint belongs to the last sector; interior ownership is half-open.
    return SectorKey(x // config.sector_m,
                     min(y // config.sector_m, config.height_m // config.sector_m - 1))


def nearby_sectors(config: WorldConfig, center: SectorKey, radius: int = 1) -> list[SectorKey]:
    """Bounded, nearest-first preparation plan, without materializing anything."""
    if type(radius) is not int or not 0 <= radius <= 4:
        raise ValueError("Preparation radius must be 0..4 sectors")
    center = canonical_sector(config, center)
    keys = {canonical_sector(config, SectorKey(center.x + dx, center.y + dy))
            for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1)
            if 0 <= center.y + dy < config.height_m // config.sector_m}
    columns = config.width_m // config.sector_m
    def priority(key):
        dx = min(abs(key.x - center.x), columns - abs(key.x - center.x))
        return (max(dx, abs(key.y - center.y)), key.y, key.x)
    return sorted(keys, key=priority)
