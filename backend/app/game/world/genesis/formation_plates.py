"""Bounded spherical plate nucleation and traceable kinematic properties."""
from dataclasses import asdict, dataclass

from .formation_config import FormationConfig, plate_scale_m
from .formation_noise import UNIT, unit_direction
from .randomness import coordinate_seed
from .sphere_topology import SurfacePoint, face_point

NUCLEATION_LEVEL = 3
MAX_PLATES = 6*4**NUCLEATION_LEVEL


@dataclass(frozen=True)
class Plate:
    slot: int
    center: tuple[int, int, int]
    axis: tuple[int, int, int]
    continental: bool
    age_myr: int
    speed_mm_year: int

    def to_dict(self) -> dict:
        return asdict(self)


def plate_from_center(seed: int, slot: int, center: tuple[int, int, int], continental_crust_ppm: int) -> Plate:
    """Frozen V3 geological marks, shared by both nucleation policies."""
    raw_axis = tuple(coordinate_seed(seed, 3, "rotation_axis", slot, i)%2001-1000 for i in range(3))
    axis = unit_direction(SurfacePoint(*(raw_axis if any(raw_axis) else (1, 0, 0))))
    return Plate(slot, center, axis,
        coordinate_seed(seed, 3, "crust", slot)%1_000_000 < continental_crust_ppm,
        20+coordinate_seed(seed, 3, "crust_age", slot)%221,
        10+coordinate_seed(seed, 3, "drift_speed", slot)%91)


def nucleate_plates(seed: int, config: FormationConfig) -> tuple[Plate, ...]:
    radius, scale = config.radius_m, plate_scale_m(config.radius_m)
    # Expected population from physical area/density; no requested plate count.
    probability = min(750_000, 4*355*radius*radius*1_000_000//(113*3*scale*scale*MAX_PLATES))
    ranks = [(coordinate_seed(seed, 3, "nucleation", slot)%1_000_000, slot) for slot in range(MAX_PLATES)]
    selected = {slot for value, slot in ranks if value < probability}
    # A kinematic partition needs two sites; this is not a minimum continent count.
    if len(selected) < 2:
        selected.update(slot for _, slot in sorted(ranks)[:2])
    plates = []
    n = 2**NUCLEATION_LEVEL
    for slot in sorted(selected):
        face, cell = divmod(slot, n*n)
        y, x = divmod(cell, n)
        u = 128+coordinate_seed(seed, 3, "site_u", slot)%768
        v = 128+coordinate_seed(seed, 3, "site_v", slot)%768
        center = unit_direction(face_point(face, x*1024+u, y*1024+v, n*1024))
        plates.append(plate_from_center(seed, slot, center, config.continental_crust_ppm))
    return tuple(plates)
