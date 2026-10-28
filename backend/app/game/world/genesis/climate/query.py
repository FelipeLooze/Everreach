"""C1 climatology readers. Climate inputs never assert runoff or river permanence."""
from math import isqrt

from ..formation_tectonics import evaluate
from .geometry import Q, interpolate, stencil, unit
from .physics import lapse, pet_milli_mm_day


def sample_climate(plan, point, *, _terrain_height=None):
    weights = stencil(point, plan.config.level)
    macro_height = interpolate(plan.heights, weights)
    height = macro_height if _terrain_height is None else _terrain_height
    maritime = interpolate(plan.maritime_ppm, weights)
    direction = unit(point)
    seasons = []
    for index in range(4):
        temperature = lapse(interpolate(plan.sea_temperature_centi_c[index], weights), height-plan.sea_level_m, plan.config)
        rain = interpolate(plan.precipitation_mm[index], weights)
        solar = interpolate(plan.insolation_ppm[index], weights)
        pet = pet_milli_mm_day(temperature, solar, plan.config)*plan.config.year_days//4000
        vector = tuple(interpolate({i: plan.wind_milli_m_s[index][i][axis] for i, _ in weights}, weights)
                       for axis in range(3))
        # Remove the interpolated radial component; no chart-dependent bearing at poles.
        radial = sum(a*b for a, b in zip(vector, direction))
        vector = tuple(v-radial*d//(Q*Q) for v, d in zip(vector, direction))
        snow_fraction = min(Q, max(0, (200-temperature)*Q//400))
        seasons.append({"index": index, "year_fraction": [1, 4], "temperature_centi_c": temperature,
            "precipitation_mm": rain, "potential_evapotranspiration_mm": pet,
            "atmospheric_moisture_index_ppm": interpolate(plan.moisture_ppm[index], weights),
            "wind_vector_milli_m_s": list(vector), "wind_speed_milli_m_s": isqrt(sum(v*v for v in vector)),
            "freezing_potential": temperature <= 0, "snowfall_potential_mm": rain*snow_fraction//Q})
    annual_rain = sum(s["precipitation_mm"] for s in seasons)
    annual_pet = sum(s["potential_evapotranspiration_mm"] for s in seasons)
    temperatures = [s["temperature_centi_c"] for s in seasons]
    return {"climate_version": plan.config.climate_version, "signature": plan.signature, "source_signature": plan.source_signature,
        "hydrology_signature": plan.hydrology_signature, "point": list(point.xyz),
        "resolution": "global_interpolation" if _terrain_height is None else "regional_v4_altitude_adjustment",
        "precipitation_resolution_level": plan.config.level, "terrain_elevation_m": height,
        "year_days": plan.config.year_days, "period_duration_days": [plan.config.year_days, 4],
        "mean_temperature_centi_c": sum(temperatures)//4,
        "seasonal_temperature_range_centi_c": max(temperatures)-min(temperatures),
        "annual_precipitation_mm": annual_rain, "annual_potential_evapotranspiration_mm": annual_pet,
        "precipitation_to_pet_ppm": annual_rain*Q//annual_pet if annual_pet else None,
        "aridity_index_ppm": max(0, annual_pet-annual_rain)*Q//annual_pet if annual_pet else None,
        "aridity_status": "demand_deficit_proxy" if annual_pet else "energy_limited_undefined",
        "continentality_ppm": Q-maritime, "seasons": seasons, "weather_event": None,
        "actual_snowpack_mm": None, "actual_ice_cover": None, "runoff_mm": None,
        "river_discharge_m3_s": None, "permanent_water": None}


def sample_regional_climate(source, plan, point):
    if source.config.generator_version != 4 or source.signature != plan.source_signature:
        raise ValueError("Regional C1 query requires its unchanged V4 source")
    height = evaluate(source.seed, source.config, source.plates, point, causes=False)["elevation_m"]
    return sample_climate(plan, point, _terrain_height=height)


def season_at_phase(sample, phase_ppm):
    """Calendar-independent periodic interpolation; precipitation is a daily rate."""
    if type(phase_ppm) is not int:
        raise ValueError("Orbital phase must be an integer ppm fraction")
    position = (phase_ppm % Q)*4
    index, fraction = divmod(position, Q)
    a, b = sample["seasons"][index], sample["seasons"][(index+1)%4]
    return {"phase_ppm": phase_ppm % Q, "period_indices": [index, (index+1)%4],
        "temperature_centi_c": (a["temperature_centi_c"]*(Q-fraction)+b["temperature_centi_c"]*fraction)//Q,
        "precipitation_period_equivalent_mm": (a["precipitation_mm"]*(Q-fraction)+b["precipitation_mm"]*fraction)//Q,
        "precipitation_milli_mm_per_day": (a["precipitation_mm"]*(Q-fraction)+b["precipitation_mm"]*fraction)*4000//(Q*sample["year_days"]),
        "weather_event": None}


def hydrology_inputs(sample, season_index):
    if type(season_index) is not int or not 0 <= season_index < 4:
        raise ValueError("Expected one of four C1 climatological periods")
    season = sample["seasons"][season_index]
    return {"kind": f"climatological_water_balance_inputs_c{sample['climate_version']}", "climate_signature": sample["signature"],
        "source_signature": sample["source_signature"], "hydrology_signature": sample["hydrology_signature"],
        "point": sample["point"], "season_index": season_index, "year_fraction": [1, 4],
        "period_duration_days": sample["period_duration_days"],
        **{k: season[k] for k in ("temperature_centi_c", "precipitation_mm", "potential_evapotranspiration_mm",
                                  "snowfall_potential_mm", "atmospheric_moisture_index_ppm")},
        "precipitation_resolution_level": sample["precipitation_resolution_level"],
        "interpretation": "potential_evapotranspiration_is_atmospheric_demand_not_actual_water_loss",
        "actual_evapotranspiration_mm": None, "available_runoff_mm": None, "storage_change_m3": None,
        "river_discharge_m3_s": None, "perennial": None, "lake_permanent": None}
