"""Pinned C1 global climatology, with no local-sector or weather generation."""
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isqrt

from ..formation_config import calibrated_scale
from ..formation_plan import cell_index
from ..formation_tectonics import evaluate
from ..sphere_topology import cell_at
from .config import ClimateConfig
from .geometry import Q, geometry
from .physics import (condensation, declinations, lapse, ocean_distances, seasonal_temperature,
                      transport, wind)


def signature(source_signature, hydrology_signature, config):
    value = [f"climate-c{config.climate_version}", source_signature, hydrology_signature, config.model_dump()]
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class ClimatePlan:
    config: ClimateConfig
    source_signature: str
    hydrology_signature: str
    signature: str
    radius_m: int
    sea_level_m: int
    maritime_length_m: int
    moisture_length_m: int
    heights: tuple
    marine: tuple
    ocean_distance_m: tuple
    maritime_ppm: tuple
    sea_temperature_centi_c: tuple
    insolation_ppm: tuple
    precipitation_mm: tuple
    moisture_ppm: tuple
    wind_milli_m_s: tuple
    transport_residual_ppm: tuple

    def to_dict(self):
        return {"kind": f"climate_c{self.config.climate_version}", "config": self.config.model_dump(),
            **{key: getattr(self, key) for key in self.__dataclass_fields__ if key != "config"},
            "representation": "four_equal_orbital_periods_climatology_not_daily_weather"}


def build_climate_plan(source, h1, config=None):
    config = config or ClimateConfig()
    if (source.config.generator_version != 4 or source.signature != h1.source_signature
            or source.config.radius_m != h1.radius_m or source.config.sea_level_m != h1.sea_level_m):
        raise ValueError("C1 requires pinned V4 terrain and its H1 reference ocean")
    g, radius, sea = geometry(config.level), source.config.radius_m, source.config.sea_level_m
    heights = tuple(evaluate(source.seed, source.config, source.plates, p, causes=False)["elevation_m"] for p in g.points)
    marine = tuple(z < sea and h1.drainage.marine[cell_index(cell_at(p, h1.config.level))]
                   for z, p in zip(heights, g.points))
    return _solve_climate(source.signature, h1.signature, radius, sea, heights, marine,
                          calibrated_scale(source.config)["plate_length_m"], config)


def _solve_climate(source_signature, h1_signature, radius, sea, heights, marine, plate_length, config):
    """Separate graph kernel also supports controlled terrain tests."""
    if config.climate_version == 3:
        from .v3 import solve
        return solve(source_signature,h1_signature,radius,sea,heights,marine,plate_length,config)
    if config.climate_version == 1:
        condensation_model = condensation
    elif config.climate_version == 2:
        from .v2 import condensation as condensation_model
    else:
        raise ValueError("Unsupported climate version")
    g = geometry(config.level)
    maritime_length = config.maritime_length_m or max(1, plate_length//3)
    moisture_length = config.moisture_length_m or max(1, 2*plate_length)
    lengths = {tuple(sorted((i, j))): max(1, isqrt(sum((a-b)**2 for a, b in zip(g.directions[i], g.directions[j])))*radius//Q)
               for i in range(len(g.points)) for j in g.adjacent[i] if i < j}
    distances = ocean_distances(g.adjacent, lengths, marine)
    maritime = tuple(0 if d is None else Q*maritime_length**2//(maritime_length+d)**2 for d in distances)
    forcing = [seasonal_temperature(direction, m, config) for direction, m in zip(g.directions, maritime)]
    sea_t = tuple(tuple(f[0][s] for f in forcing) for s in range(4))
    solar = tuple(tuple(f[1][s] for f in forcing) for s in range(4))
    all_precip, all_moisture, all_wind, residuals = [], [], [], []
    for season, declination in enumerate(declinations(config)):
        winds = tuple(wind(d, declination, config) for d in g.directions)
        stencils, retention, fractions, source = [], [], [], []
        for i, adjacent in enumerate(g.adjacent):
            pairs = []
            for j in adjacent:
                delta = tuple(b-a for a, b in zip(g.directions[i], g.directions[j]))
                dot = sum(a*b for a, b in zip(delta, winds[i]))
                score = max(0, -dot)*Q//max(1, isqrt(sum(a*a for a in delta)))
                if score:
                    pairs.append((j, score))
            pairs = tuple(pairs or ((j, 1) for j in adjacent))
            stencils.append(pairs)
            total = sum(w for _, w in pairs)
            span = sum(lengths[tuple(sorted((i, j)))]*w for j, w in pairs)//total
            upstream = sum(heights[j]*w for j, w in pairs)//total
            retention.append(moisture_length*Q//(moisture_length+span))
            fractions.append(condensation_model(g.directions[i], declination, max(0, heights[i]-upstream), config))
            temperature = lapse(sea_t[season][i], heights[i]-sea, config)
            supply = min(Q, max(150_000, 250_000+max(0, temperature+1000)*150)) if marine[i] else 0
            # Potential freezing suppresses, but does not claim actual sea ice.
            if temperature < 0:
                supply = supply*max(100_000, Q+temperature*200)//Q
            source.append(supply)
        moisture, rain, residual = transport(stencils, retention, fractions, source, config.transport_iterations)
        all_precip.append(tuple(value*config.rain_scale_milli_mm_per_day*config.year_days//(Q*4000) for value in rain))
        all_moisture.append(moisture)
        all_wind.append(winds)
        residuals.append(residual)
    plan = ClimatePlan(config, source_signature, h1_signature, signature(source_signature, h1_signature, config),
        radius, sea, maritime_length, moisture_length, tuple(heights), tuple(marine), distances, maritime, sea_t,
        solar, tuple(all_precip), tuple(all_moisture), tuple(all_wind), tuple(residuals))
    validate(plan)
    return plan


def validate(plan):
    count = len(geometry(plan.config.level).points)
    if (plan.signature != signature(plan.source_signature, plan.hydrology_signature, plan.config)
            or not 1000 <= plan.radius_m <= 10**12 or not -10_000 <= plan.sea_level_m <= 10_000
            or plan.maritime_length_m <= 0 or plan.moisture_length_m <= 0):
        raise ValueError("C1 source, configuration or scale mismatch")
    for name in ("heights", "marine", "ocean_distance_m", "maritime_ppm"):
        if len(getattr(plan, name)) != count:
            raise ValueError("Invalid C1 global sampling budget")
    if any(type(z) is not int for z in plan.heights) or any(type(m) is not bool for m in plan.marine):
        raise ValueError("Invalid C1 terrain/ocean data")
    for ocean, height, distance, maritime in zip(plan.marine, plan.heights, plan.ocean_distance_m, plan.maritime_ppm):
        if (distance is not None and (type(distance) is not int or distance < 0)) or not 0 <= maritime <= Q:
            raise ValueError("Invalid maritime field")
        expected = 0 if distance is None else Q*plan.maritime_length_m**2//(plan.maritime_length_m+distance)**2
        if (type(maritime) is not int or maritime != expected or (ocean and (height >= plan.sea_level_m or distance != 0))
                or (not ocean and distance == 0)):
            raise ValueError("Maritime index does not match the pinned distance")
    for name in ("sea_temperature_centi_c", "insolation_ppm", "precipitation_mm", "moisture_ppm", "wind_milli_m_s"):
        values = getattr(plan, name)
        if len(values) != 4 or any(len(season) != count for season in values):
            raise ValueError("Invalid C1 seasonal arrays")
        for season in values:
            for value in season:
                if name == "wind_milli_m_s":
                    if len(value) != 3 or any(type(v) is not int or abs(v) > 2*plan.config.wind_scale_milli_m_s for v in value):
                        raise ValueError("Invalid wind vector")
                elif type(value) is not int or (name in ("insolation_ppm", "moisture_ppm") and not 0 <= value <= Q) or (
                        name == "precipitation_mm" and value < 0):
                    raise ValueError("Invalid C1 scalar field")
    if len(plan.transport_residual_ppm) != 4 or any(type(d) is not int or not 0 <= d <= Q for d in plan.transport_residual_ppm):
        raise ValueError("Invalid transport residual")


def load_climate_plan(data, source_signature, hydrology_signature, radius_m, sea_level_m):
    from .dispatch import parse_climate_config
    config = parse_climate_config(data["config"])
    if (data.get("kind") != f"climate_c{config.climate_version}" or data.get("source_signature") != source_signature
            or data.get("hydrology_signature") != hydrology_signature or data.get("radius_m") != radius_m
            or data.get("sea_level_m") != sea_level_m):
        raise ValueError("C1 persisted provenance mismatch")
    scalars = ("source_signature", "hydrology_signature", "signature", "radius_m", "sea_level_m", "maritime_length_m", "moisture_length_m")
    arrays = ("heights", "marine", "ocean_distance_m", "maritime_ppm", "transport_residual_ppm")
    seasonal = ("sea_temperature_centi_c", "insolation_ppm", "precipitation_mm", "moisture_ppm")
    plan = ClimatePlan(config, **{k: data[k] for k in scalars}, **{k: tuple(data[k]) for k in arrays},
        **{k: tuple(tuple(s) for s in data[k]) for k in seasonal},
        wind_milli_m_s=tuple(tuple(tuple(v) for v in s) for s in data["wind_milli_m_s"]))
    validate(plan)
    if config.climate_version == 3:
        from .v3 import load
        return load(data,plan)
    return plan
