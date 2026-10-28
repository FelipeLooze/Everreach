"""C2 adds only prescribed extratropical ascent to the existing condensation law."""
from typing import Literal
from pydantic import Field

from .config import ClimateConfig
from .geometry import Q
from .physics import condensation as condensation_c1, sine_mdeg


class ClimateConfigV2(ClimateConfig):
    climate_version: Literal[2] = 2
    extratropical_condensation_ppm: int = Field(default=250_000, ge=0, le=700_000)


def condensation(direction, declination, rise_m, config):
    """Compact ascent between the prescribed Hadley edge and poles, peak at polar edge.

    This is a stationary RPG circulation closure, not a synoptic weather solver.
    Ocean supply, temperature, PET, wind, distance attenuation and orography stay C1.
    """
    latitude = min(Q, abs(direction[2]))
    hadley, polar = sine_mdeg(config.hadley_edge_mdeg), sine_mdeg(config.polar_edge_mdeg)
    if latitude <= hadley:
        ascent = 0
    elif latitude <= polar:
        ascent = (latitude-hadley)*Q//(polar-hadley)
    else:
        ascent = (Q-latitude)*Q//(Q-polar)
    return min(850_000, condensation_c1(direction, declination, rise_m, config)
               + ascent*config.extratropical_condensation_ppm//Q)
