"""Conservative integer buckets and a gated projection of the EXISTING H1 DAG."""
from dataclasses import dataclass
from types import MappingProxyType

from .config import WaterConfig

Q = 1_000_000
STORES = ("snow", "soil", "surface", "depression", "channel", "unresolved")
FLUXES = ("precipitation", "pet", "snowfall", "melt", "infiltration", "soil_release", "local_runoff",
          "incoming", "evapotranspiration", "outflow", "ocean_export", "potential_overflow")


@dataclass(frozen=True)
class WaterSolution:
    # Final model year only; earlier cycles carry all stocks without resetting.
    initial_stores: tuple
    periods: tuple
    warmup_years: int
    initial_condition: str = "all_stores_dry_before_bounded_warmup"

    def to_dict(self):
        return {"initial_stores": [list(values) for values in self.initial_stores],
            "periods": [{"fluxes": {k: list(v) for k, v in p["fluxes"].items()},
                "stores": {k: list(v) for k, v in p["stores"].items()}, "totals": dict(p["totals"])} for p in self.periods],
            "warmup_years": self.warmup_years, "initial_condition": self.initial_condition}


def freeze_period(period):
    return MappingProxyType({"fluxes": MappingProxyType({k: tuple(v) for k, v in period["fluxes"].items()}),
        "stores": MappingProxyType({k: tuple(v) for k, v in period["stores"].items()}),
        "totals": MappingProxyType(dict(period["totals"]))})


def solve(areas, marine, parents, rank, precipitation, pet, snowfall, temperatures, capacities,
          route_open, distances, year_days, config: WaterConfig):
    count = len(areas)
    if (not count or any(len(v) != count for v in (marine, parents, rank, capacities, route_open, distances))
            or sorted(rank) != list(range(count))):
        raise ValueError("Invalid W1 node budget or H1 rank")
    for i, parent in enumerate(parents):
        if parent < -1 or parent >= count or (parent >= 0 and rank[parent] >= rank[i]):
            raise ValueError("W1 cannot route a cyclic/non-H1 receiver graph")
        if type(areas[i]) is not int or areas[i] <= 0 or capacities[i] < 0 or distances[i] < 0:
            raise ValueError("Invalid physical water area/capacity/distance")
    for values in (precipitation, pet, snowfall, temperatures):
        if len(values) != 4 or any(len(row) != count or any(type(v) is not int for v in row) for row in values):
            raise ValueError("W1 needs four integer climatological periods")
    if any(p < 0 or e < 0 or not 0 <= s <= p for pr, pe, sn in zip(precipitation, pet, snowfall)
           for p, e, s in zip(pr, pe, sn)):
        raise ValueError("Invalid precipitation/PET/snow partition")
    stocks = {name: [0]*count for name in STORES}
    order = sorted(range(count), key=lambda i: rank[i], reverse=True)
    path_m = max(1, config.channel_velocity_mm_s*year_days*86400//4000)
    fraction = [Q*path_m//(path_m+distance) for distance in distances]
    output, initial = [], None
    for year in range(config.warmup_years+1):
        if year == config.warmup_years:
            initial = tuple(tuple(stocks[name]) for name in STORES)
        for season in range(4):
            before = [sum(stocks[name][i] for name in STORES) for i in range(count)]
            flux = {name: [0]*count for name in FLUXES}
            for i in order:
                incoming = flux["incoming"][i]
                if marine[i]:
                    flux["ocean_export"][i] = incoming
                    continue  # ocean is a sink boundary; its rain/evap is outside this domain
                area = areas[i]
                p, demand, snow = precipitation[season][i]*area, pet[season][i]*area, snowfall[season][i]*area
                flux["precipitation"][i], flux["pet"][i], flux["snowfall"][i] = p, demand, snow
                stocks["snow"][i] += snow
                melt_limit = area*max(0, temperatures[season][i])*config.snow_melt_milli_mm_per_degree_day*year_days//400_000
                melt = min(stocks["snow"][i], melt_limit)
                stocks["snow"][i] -= melt
                flux["melt"][i] = melt
                liquid = p-snow+melt+stocks["surface"][i]
                factor = config.frozen_soil_factor_ppm if temperatures[season][i] <= 0 else Q
                infiltration_limit = area*config.infiltration_mm_per_day*year_days*factor//(4*Q)
                infiltration = min(liquid, max(0, config.soil_capacity_mm*area-stocks["soil"][i]), infiltration_limit)
                stocks["soil"][i] += infiltration
                liquid -= infiltration
                flux["infiltration"][i] = infiltration
                # Demand consumes only accessible liquid/soil. Snow is not an ET source.
                exposed_et = min(liquid, demand)
                liquid -= exposed_et
                soil_et = min(stocks["soil"][i], demand-exposed_et)
                stocks["soil"][i] -= soil_et
                actual_et = exposed_et+soil_et
                k = config.soil_release_ppm_per_day*year_days*factor//Q
                release = stocks["soil"][i]*k//(4*Q+k)
                stocks["soil"][i] -= release
                flux["soil_release"][i] = release
                liquid += release
                stocks["surface"][i] = min(liquid, config.surface_capacity_mm*area)
                local = liquid-stocks["surface"][i]
                flux["local_runoff"][i] = local
                # Capacity is a declared H1 column approximation, never bathymetry.
                reservoir = stocks["depression"][i]+local+incoming
                capacity = capacities[i]
                fill = min(Q, reservoir*Q//capacity) if capacity else 0
                evaporation_limit = (demand-actual_et)*config.reservoir_wetted_area_ppm*fill//(Q*Q)
                reservoir_et = min(reservoir, evaporation_limit)
                reservoir -= reservoir_et
                actual_et += reservoir_et
                stocks["depression"][i] = min(reservoir, capacity)
                available = reservoir-stocks["depression"][i]
                flux["potential_overflow"][i] = available if capacity else 0
                flux["evapotranspiration"][i] = actual_et
                channel = stocks["channel"][i]+available
                parent = parents[i]
                if route_open[i] and parent >= 0:
                    outflow = channel*fraction[i]//Q
                    stocks["channel"][i] = channel-outflow
                    flux["outflow"][i] = outflow
                    flux["incoming"][parent] += outflow
                else:
                    stocks["unresolved"][i] += channel
                    stocks["channel"][i] = 0
                after = sum(stocks[name][i] for name in STORES)
                if before[i]+p+incoming != actual_et+flux["outflow"][i]+after:
                    raise ValueError("W1 node water conservation failed")
            totals = {name: sum(values) for name, values in flux.items()}
            end_total = sum(sum(values) for values in stocks.values())
            start_total = sum(before)
            if start_total+totals["precipitation"] != totals["evapotranspiration"]+totals["ocean_export"]+end_total:
                raise ValueError("W1 global water conservation failed")
            if year == config.warmup_years:
                output.append({"fluxes": {name: tuple(values) for name, values in flux.items()},
                    "stores": {name: tuple(values) for name, values in stocks.items()},
                    "totals": {**totals, "start_storage": start_total, "end_storage": end_total, "residual_liters": 0}})
    result = WaterSolution(initial, tuple(freeze_period(p) for p in output), config.warmup_years)
    validate(result, areas, marine, parents, rank, config)
    return result


def validate(result, areas, marine, parents, rank, config):
    count = len(areas)
    if (len(result.periods) != 4 or len(result.initial_stores) != len(STORES) or result.warmup_years != config.warmup_years
            or result.initial_condition != "all_stores_dry_before_bounded_warmup"):
        raise ValueError("Invalid W1 persisted temporal budget")
    previous = dict(zip(STORES, result.initial_stores))
    for period in result.periods:
        flux, stores, totals = period["fluxes"], period["stores"], period["totals"]
        if set(flux) != set(FLUXES) or set(stores) != set(STORES):
            raise ValueError("Invalid W1 compartments")
        for values in (*previous.values(), *flux.values(), *stores.values()):
            if len(values) != count or any(type(v) is not int or v < 0 for v in values):
                raise ValueError("Invalid W1 quantity")
        incoming = [0]*count
        for i, parent in enumerate(parents):
            if parent >= 0:
                if rank[parent] >= rank[i]:
                    raise ValueError("W1 receiver cycle")
                incoming[parent] += flux["outflow"][i]
            elif flux["outflow"][i]:
                raise ValueError("Water cannot leave through a nonexistent receiver")
        if tuple(incoming) != tuple(flux["incoming"]):
            raise ValueError("Duplicated/missing tributary water")
        for i in range(count):
            before = sum(previous[name][i] for name in STORES)
            after = sum(stores[name][i] for name in STORES)
            if (before+flux["precipitation"][i]+incoming[i] != after+flux["evapotranspiration"][i]
                    +flux["outflow"][i]+flux["ocean_export"][i] or flux["evapotranspiration"][i] > flux["pet"][i]):
                raise ValueError("W1 persisted water conservation/PET failed")
            if (flux["snowfall"][i] > flux["precipitation"][i]
                    or stores["snow"][i] != previous["snow"][i]+flux["snowfall"][i]-flux["melt"][i]):
                raise ValueError("W1 snow/melt partition mismatch")
            if (stores["soil"][i] > config.soil_capacity_mm*areas[i] or
                    stores["surface"][i] > config.surface_capacity_mm*areas[i]):
                raise ValueError("Water exceeds declared soil/surface capacity")
            if marine[i] and (after or flux["precipitation"][i] or flux["ocean_export"][i] != incoming[i]):
                raise ValueError("Ocean boundary cannot generate river water")
        for name, values in flux.items():
            if totals.get(name) != sum(values):
                raise ValueError("W1 total does not match node ledger")
        start = sum(sum(values) for values in previous.values())
        end = sum(sum(values) for values in stores.values())
        if (totals.get("start_storage") != start or totals.get("end_storage") != end
                or start+totals["precipitation"] != end+totals["evapotranspiration"]+totals["ocean_export"]
                or totals.get("residual_liters") != 0):
            raise ValueError("W1 global ledger mismatch")
        previous = stores
