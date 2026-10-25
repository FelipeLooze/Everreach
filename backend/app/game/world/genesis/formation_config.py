"""V3 scale policy. Old configuration classes and their defaults stay intact."""
from math import isqrt
from typing import Literal

from pydantic import Field, model_validator

from .sphere_config import SphereConfig


def plate_scale_m(radius_m: int) -> int:
    # sqrt(radius) scaling preserves useful physical structure sizes; radius/8
    # prevents the fixed global planning budget being overwhelmed at huge radii.
    return min(radius_m, max(isqrt(16_000_000_000_000 * radius_m // 6_371_000), radius_m // 8))


def _level_for_span(radius_m: int, target_m: int, minimum: int, maximum: int) -> int:
    # ceil(log2(pi*R/(2*target))) using integer pi ~= 355/113.
    level = minimum
    while level < maximum and 355*radius_m > 226*target_m*(2**level):
        level += 1
    return level


class FormationConfig(SphereConfig):
    config_version: Literal[3] = 3
    generator_version: Literal[3] = 3
    radius_m: int = Field(default=63_710_000, ge=1_000, le=1_000_000_000_000)
    target_sector_m: int = Field(default=16_000, ge=1, le=1_000_000_000)
    # Here macro_level is the connected-component planning resolution, not v2 noise frequency.
    macro_level: int = Field(default=5, ge=2, le=5)
    continental_crust_ppm: int = Field(default=430_000, ge=0, le=1_000_000)

    @model_validator(mode="before")
    @classmethod
    def automatic_resolution(cls, data):
        if not isinstance(data, dict):
            return data
        values = dict(data)
        radius = values.get("radius_m", 63_710_000)
        target = values.get("target_sector_m", 16_000)
        if type(radius) is int and radius > 0 and type(target) is int and target > 0:
            values.setdefault("sector_level", _level_for_span(radius, target, 0, 24))
            values.setdefault("macro_level", _level_for_span(radius, max(1, plate_scale_m(radius)//3), 2, 5))
        return values


def calibrated_scale(config: FormationConfig) -> dict:
    plate = plate_scale_m(config.radius_m)
    nominal_sector = 355*config.radius_m // (226*2**config.sector_level)
    return {"plate_length_m": plate, "orogen_width_m": max(1, plate//25),
            "regional_wavelength_m": max(1, plate//3), "detail_wavelength_m": max(1, plate//40),
            "nominal_sector_span_m": nominal_sector,
            "sector_resolution_limited": nominal_sector > config.target_sector_m,
            "macro_cells": 6*4**config.macro_level,
            "nominal_identity_span_m": 355*config.radius_m // (226*2**config.macro_level),
            "macro_resolution_limited": 355*config.radius_m > 226*max(1, plate//3)*2**config.macro_level}
