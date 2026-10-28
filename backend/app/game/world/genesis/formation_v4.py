"""V4 changes only site sampling; shared V3 geology/metric remain frozen."""
from math import isqrt
from typing import Literal

from .formation_config import FormationConfig, plate_scale_m
from .formation_noise import unit_direction
from .formation_plates import MAX_PLATES, NUCLEATION_LEVEL, Plate, plate_from_center
from .randomness import coordinate_seed
from .sphere_topology import face_point


class FormationConfigV4(FormationConfig):
    config_version: Literal[4] = 4
    generator_version: Literal[4] = 4


# round(cell_solid_angle(CellKey(0,3,x,y))*10**12), mirrored by symmetry.
# Frozen authoritatively, tested against sphere_area; no runtime libm dependency.
AREA_QUADRANT = (
    (15568607867, 19787706428, 23782777643, 26310653076),
    (19787706428, 26311566872, 32938305777, 37360897110),
    (23782777643, 32938305777, 42857347310, 49821533767),
    (26310653076, 37360897110, 49821533767, 58857505947),
)
AREA_SCALE = 10**12
RANDOM_RANGE = 2**63
SITE_RESOLUTION = 2**20
MAX_SITE_ATTEMPTS = 128


def cell_area_weight(slot: int) -> int:
    if type(slot) is not int or not 0 <= slot < MAX_PLATES:
        raise ValueError("Invalid nucleation slot")
    y, x = divmod(slot % 64, 8)
    return AREA_QUADRANT[min(y, 7-y)][min(x, 7-x)]


def activation_thresholds(config: FormationConfigV4) -> tuple[int, ...]:
    """One global intensity, never cell-wise probability clipping."""
    radius, scale = config.radius_m, plate_scale_m(config.radius_m)
    expected_ppm = min(750_000, 4*355*radius*radius*1_000_000//(113*3*scale*scale*MAX_PLATES))
    weights = tuple(cell_area_weight(slot) for slot in range(MAX_PLATES))
    total, maximum = sum(weights), max(weights)
    return tuple(min(expected_ppm*MAX_PLATES*w*RANDOM_RANGE//(1_000_000*total),
                     95*w*RANDOM_RANGE//(100*maximum)) for w in weights)


def sample_center(seed: int, slot: int) -> tuple[int, int, int]:
    """Area-uniform conditional sampling via integer radial-chart Jacobian.

    Failure is explicit at the fixed budget, never a biased planar fallback.
    Each attempt has acceptance > 1/2 on this fixed level-3 grid.
    """
    cell_area_weight(slot)  # strict address validation
    n = 2**NUCLEATION_LEVEL
    face, cell = divmod(slot, n*n)
    y, x = divmod(cell, n)
    denominator = n*2*SITE_RESOLUTION
    def nearest_axis(index):
        lo, hi = 4*index*SITE_RESOLUTION-denominator, 4*(index+1)*SITE_RESOLUTION-denominator
        return 0 if lo <= 0 <= hi else min(abs(lo), abs(hi))
    minimum = denominator**2+nearest_axis(x)**2+nearest_axis(y)**2
    for attempt in range(MAX_SITE_ATTEMPTS):
        u = x*2*SITE_RESOLUTION+2*(coordinate_seed(seed, 4, "site_u", slot, attempt)%SITE_RESOLUTION)+1
        v = y*2*SITE_RESOLUTION+2*(coordinate_seed(seed, 4, "site_v", slot, attempt)%SITE_RESOLUTION)+1
        squared = denominator**2+(2*u-denominator)**2+(2*v-denominator)**2
        threshold = isqrt(minimum**3*RANDOM_RANGE**2//squared**3)
        if coordinate_seed(seed, 4, "surface_accept", slot, attempt) < threshold:
            return unit_direction(face_point(face, u, v, denominator))
    raise ValueError("V4 spherical site sampling exceeded its fixed attempt budget")


def nucleate_plates_v4(seed: int, config: FormationConfigV4) -> tuple[Plate, ...]:
    thresholds = activation_thresholds(config)
    selected = {slot for slot, threshold in enumerate(thresholds)
                if coordinate_seed(seed, 4, "nucleation", slot) < threshold}
    # Structural minimum only; choose missing sites by area, not uniform index.
    while len(selected) < 2:
        remaining = [(slot, cell_area_weight(slot)) for slot in range(MAX_PLATES) if slot not in selected]
        total = sum(weight for _, weight in remaining)
        ticket = coordinate_seed(seed, 4, "structural_fallback", len(selected))*total//RANDOM_RANGE
        for slot, weight in remaining:
            if ticket < weight:
                selected.add(slot)
                break
            ticket -= weight
    return tuple(plate_from_center(seed, slot, sample_center(seed, slot), config.continental_crust_ppm)
                 for slot in sorted(selected))
