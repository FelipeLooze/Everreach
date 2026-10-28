"""Area-weighted offline diagnostics. These indices do not create biomes."""
from collections import defaultdict
from collections import deque
from functools import lru_cache
from math import isqrt

from ..sphere_area import rectangle_solid_angle
from .geometry import Q, geometry
from .physics import condensation, declinations, lapse, pet_milli_mm_day


def upstream_stencil(plan, node, season):
    g = geometry(plan.config.level)
    vector, pairs = plan.wind_milli_m_s[season][node], []
    for other in g.adjacent[node]:
        delta = tuple(b-a for a, b in zip(g.directions[node], g.directions[other]))
        dot = sum(a*b for a, b in zip(delta, vector))
        score = max(0, -dot)*Q//max(1, isqrt(sum(a*a for a in delta)))
        if score:
            pairs.append((other, score))
    return tuple(pairs or ((other, 1) for other in g.adjacent[node]))


@lru_cache(maxsize=2)
def area_weights(level):
    g, n = geometry(level), 2**level
    weights = [0.0]*len(g.points)
    for face in g.faces:
        for y in range(n):
            for x in range(n):
                area = rectangle_solid_angle(2*x/n-1, 2*y/n-1, 2*(x+1)/n-1, 2*(y+1)/n-1)/4
                for dx, dy in ((0, 0), (0, 1), (1, 0), (1, 1)):
                    weights[face[(y+dy)*(n+1)+x+dx]] += area
    return tuple(weights)


class Summary:
    def __init__(self):
        self.area = self.rain = self.pet = self.temperature = self.amplitude = 0.0
        self.classes = defaultdict(float)
        self.season_rain, self.season_temperature = [0.0]*4, [0.0]*4
        self.peak = self.cold = 0.0

    def add(self, weight, rain, pet, temperature):
        p, e = sum(rain), sum(pet)
        self.area += weight
        self.rain += weight*p
        self.pet += weight*e
        self.temperature += weight*sum(temperature)/400
        self.amplitude += weight*(max(temperature)-min(temperature))/100
        category = ("energy_limited" if e == 0 else "humid_p_ge_pet" if p >= e else
                    "moderate_deficit" if 2*p >= e else "semiarid_index" if 4*p >= e else "dry_index")
        self.classes[category] += weight
        self.peak += weight*max(rain)/p if p else 0.0
        self.cold += weight*(0 <= sum(temperature)//4 <= 2000)
        for season in range(4):
            self.season_rain[season] += weight*rain[season]
            self.season_temperature[season] += weight*temperature[season]/100

    def result(self):
        if not self.area:
            return {"solid_angle": 0, "mean_precipitation_mm": None}
        return {"solid_angle": self.area, "mean_precipitation_mm": self.rain/self.area,
            "mean_pet_mm": self.pet/self.area, "mean_temperature_c": self.temperature/self.area,
            "mean_temperature_amplitude_c": self.amplitude/self.area,
            "index_area_fractions": {key: self.classes[key]/self.area for key in
                ("humid_p_ge_pet", "moderate_deficit", "semiarid_index", "dry_index", "energy_limited")},
            "temperate_temperature_0_to_20c_fraction": self.cold/self.area,
            "mean_peak_period_fraction_including_dry_zero": self.peak/self.area,
            "period_precipitation_mm": [value/self.area for value in self.season_rain],
            "period_temperature_c": [value/self.area for value in self.season_temperature]}


def report(plan):
    g, weights = geometry(plan.config.level), area_weights(plan.config.level)
    summaries = defaultdict(Summary)
    latitude_edges = (258819, 500000, 707107, 866025, 965926, Q+1)
    latitude_labels = ("00-15", "15-30", "30-45", "45-60", "60-75", "75-90")
    for i, height in enumerate(plan.heights):
        rain = [plan.precipitation_mm[s][i] for s in range(4)]
        ts = [lapse(plan.sea_temperature_centi_c[s][i], height-plan.sea_level_m, plan.config) for s in range(4)]
        pet = [pet_milli_mm_day(ts[s], plan.insolation_ppm[s][i], plan.config)*plan.config.year_days//4000 for s in range(4)]
        surface = "land" if height >= plan.sea_level_m else "reference_ocean" if plan.marine[i] else "disconnected_below_datum"
        lat = next(label for limit, label in zip(latitude_edges, latitude_labels) if abs(g.directions[i][2]) < limit)
        keys = ["global", f"surface/{surface}", f"latitude/{surface}/{lat}"]
        if surface == "land":
            d = plan.ocean_distance_m[i]
            distance = ("no_ocean" if d is None else "0-1000km" if d < 1_000_000 else
                        "1000-3000km" if d < 3_000_000 else "3000-10000km" if d < 10_000_000 else "10000km+")
            normalized = ("no_ocean" if d is None else "0-0.5L" if 2*d < plan.maritime_length_m else
                "0.5-1L" if d < plan.maritime_length_m else "1-2L" if d < 2*plan.maritime_length_m else
                "2-4L" if d < 4*plan.maritime_length_m else "4L+")
            altitude = "0-500m" if height-plan.sea_level_m < 500 else "500-1500m" if height-plan.sea_level_m < 1500 else "1500-3000m" if height-plan.sea_level_m < 3000 else "3000m+"
            keys.extend((f"ocean_distance/{distance}", f"normalized_ocean_distance/{normalized}", f"altitude/{altitude}"))
        for key in keys:
            summaries[key].add(weights[i], rain, pet, ts)
        if surface == "land":
            for season in range(4):
                pairs = upstream_stencil(plan, i, season)
                upstream = sum(plan.heights[j]*w for j, w in pairs)//sum(w for _, w in pairs)
                rise = height-upstream
                exposure = "windward_rise_above_300m" if rise > 300 else "lee_fall_below_minus_300m" if rise < -300 else "low_gradient"
                # A separate per-period exposure table; values are period equivalents.
                summaries[f"wind_exposure/period_{season}/{exposure}"].add(weights[i],
                    [rain[season]]*4, [pet[season]]*4, [ts[season]]*4)
    return {"climate_version": plan.config.climate_version, "signature": plan.signature,
        "source_signature": plan.source_signature, "hydrology_signature": plan.hydrology_signature,
        "radius_m": plan.radius_m, "level": plan.config.level, "vertices": len(g.points),
        "transport_residual_ppm": list(plan.transport_residual_ppm),
        "area_method": "exact_cell_solid_angle_quarter_distributed_to_shared_vertices",
        "index_definitions": {"humid": "P/PET >= 1", "moderate_deficit": "0.5 <= P/PET < 1",
            "semiarid": "0.25 <= P/PET < 0.5", "dry": "P/PET < 0.25", "energy_limited": "PET = 0",
            "temperate": "annual mean air temperature 0..20 C; overlaps moisture indices; no biome"},
        "groups": {key: summary.result() for key, summary in sorted(summaries.items())},
        "transport_audit": transport_audit(plan)}


def transport_audit(plan):
    """No solver: trace prescribed upwind source access and per-link losses."""
    g, weights = geometry(plan.config.level), area_weights(plan.config.level)
    model = condensation
    if plan.config.climate_version == 2:
        from .v2 import condensation as model
    result = []
    for season, declination in enumerate(declinations(plan.config)):
        reverse = [[] for _ in g.points]
        groups = defaultdict(lambda: defaultdict(float))
        for i, height in enumerate(plan.heights):
            pairs = upstream_stencil(plan, i, season)
            total = sum(w for _, w in pairs)
            span = sum(max(1, isqrt(sum((a-b)**2 for a, b in zip(g.directions[i], g.directions[j])))*plan.radius_m//Q)*w
                       for j, w in pairs)//total
            upstream = sum(plan.heights[j]*w for j, w in pairs)//total
            fraction = model(g.directions[i], declination, max(0, height-upstream), plan.config)
            distance_retention = plan.moisture_length_m*Q//(plan.moisture_length_m+span)
            if plan.config.climate_version == 3:
                from .v3 import rain_fraction,exp_negative
                fraction=rain_fraction(g.directions[i],declination,max(0,height-upstream),span,plan.condensation_length_m,plan.config)
                distance_retention=exp_negative(span*Q//plan.moisture_length_m)
            temperature = lapse(plan.sea_temperature_centi_c[season][i], height-plan.sea_level_m, plan.config)
            supply = min(Q, max(150_000, 250_000+max(0, temperature+1000)*150)) if plan.marine[i] else 0
            if temperature < 0:
                supply = supply*max(100_000, Q+temperature*200)//Q
            surface = "land" if height >= plan.sea_level_m else "reference_ocean" if plan.marine[i] else "disconnected_below_datum"
            row, area = groups[surface], weights[i]
            row["solid_angle"] += area
            row["mean_ocean_source_index_ppm"] += area*supply
            row["mean_distance_retention_ppm"] += area*distance_retention
            row["mean_condensation_loss_ppm"] += area*fraction
            row["mean_transport_step_m"] += area*span
            for j, _ in pairs:
                reverse[j].append(i)
        steps = {i: 0 for i, ocean in enumerate(plan.marine) if ocean}
        queue = deque(steps)
        while queue:
            i = queue.popleft()
            for other in reverse[i]:
                if other not in steps:
                    steps[other] = steps[i]+1
                    queue.append(other)
        land = [i for i, height in enumerate(plan.heights) if height >= plan.sea_level_m]
        land_area = sum(weights[i] for i in land)
        result.append({"period": season, "land_unreachable_from_ocean_fraction":
            sum(weights[i] for i in land if i not in steps)/land_area if land_area else None,
            "land_source_path_longer_than_iterations_fraction": sum(weights[i] for i in land
                if i in steps and steps[i] > plan.config.transport_iterations)/land_area if land_area else None,
            "max_source_path_steps": max(steps.values(), default=None),
            "groups": {key: {field: value/row["solid_angle"] if field != "solid_angle" else value
                for field, value in row.items()} for key, row in groups.items()}})
    return result
