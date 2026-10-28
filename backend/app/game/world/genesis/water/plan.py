"""W1 authority: immutable forcing, fixed HR1 evidence and conserved quantities."""
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isqrt

from ..climate.geometry import unit
from ..climate.query import sample_climate, hydrology_inputs
from ..hydrology.geometry import geometry
from ..hydrology.regional import RegionalHydrologyConfig, regional_signature, validate_region, compare_regional_connection
from .balance import WaterSolution, freeze_period, solve, validate as validate_balance, STORES
from .config import WaterConfig,parse_water_config,check_climate_contract

MAX_EVIDENCE_REGIONS = 32
SUPPORT = ("ocean_boundary", "closed_sink", "overland_refinement_pending", "regional_validation_pending",
           "hr1_incompatible", "storage_capacity_unresolved", "bilateral_downhill_validated")


def checksum(data):
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def signature(h1_signature, climate_signature, hr_signature, config, manifest):
    return checksum(["water-w1", h1_signature, climate_signature, hr_signature, config.model_dump(), manifest])[:24]


def compile_evidence(h1, hr_config, regions):
    if len(regions) > MAX_EVIDENCE_REGIONS:
        raise ValueError("W1 pins at most 32 explicit HR1 regions; never prepares the globe")
    expected = regional_signature(h1, hr_config)
    by_node = {}
    g = geometry(h1.config.level)
    for region in regions:
        validate_region(region)
        node = region["node"]
        if (node in by_node or not 0 <= node < len(h1.heights) or region["source_signature"] != h1.source_signature
                or region["hydrology_signature"] != h1.signature or region["signature"] != expected
                or region["config"] != hr_config.model_dump() or region["junction"]["point"] != list(g.points[node].xyz)
                or region["junction"]["potential_head_m"] != h1.drainage.head[node]):
            raise ValueError("W1 HR1 evidence does not match its fixed geographic authority")
        by_node[node] = region
    manifest = tuple((node, checksum(region)) for node, region in sorted(by_node.items()))
    support, ports = [], []
    for node, parent in enumerate(h1.drainage.parent):
        port_id = None
        if h1.drainage.marine[node]:
            state = "ocean_boundary"
        elif parent < 0:
            state = "closed_sink"
        elif node not in h1.channel_index:
            state = "overland_refinement_pending"
        elif node not in by_node or parent not in by_node:
            state = "regional_validation_pending"
        else:
            first, second = by_node[node], by_node[parent]
            port = next((p for p in first["ports"] if p["source_node"] == node), None)
            if port is None:
                raise ValueError("HR1 evidence omits an existing H1 edge")
            port_id = port["id"]
            comparison = compare_regional_connection(first, second, port_id)
            state = "bilateral_downhill_validated" if comparison["status"] == "connected_sampled_potential" else "hr1_incompatible"
            if state == "bilateral_downhill_validated":
                for region in (first, second):
                    route = next(r for r in region["routes"] if r["port_id"] == port_id)
                    segments = {s["id"]: s for s in region["segments"]}
                    unknown = False
                    for sid in route["segment_ids"]:
                        segment = segments[sid]
                        for raised, head in zip(segment["storage_raise_m"], segment["potential_head_profile_m"]):
                            # The prescribed connected ocean already supplies its
                            # boundary stage; it is never an upstream water source.
                            marine_stage = h1.drainage.marine[region["node"]] and head <= h1.sea_level_m
                            unknown |= raised > 0 and not marine_stage
                    if unknown:
                        state = "storage_capacity_unresolved"
        support.append(state)
        ports.append(port_id)
    return manifest, tuple(support), tuple(ports)


@dataclass(frozen=True)
class WaterPlan:
    config: WaterConfig
    hydrology: object
    climate_signature: str
    hr_signature: str
    signature: str
    manifest: tuple
    support: tuple
    port_ids: tuple
    capacities_liters: tuple
    precipitation_mm: tuple
    pet_mm: tuple
    snowfall_mm: tuple
    temperatures_centi_c: tuple
    year_days: int
    solution: WaterSolution

    def identifier(self, kind, index):
        return f"water-w1:{self.signature}:{kind}:{index}"

    def to_dict(self):
        return {"kind": "water_balance_w1", "water_version": 1, "config": self.config.model_dump(),
            "source_signature": self.hydrology.source_signature, "hydrology_signature": self.hydrology.signature,
            "climate_signature": self.climate_signature, "hr_signature": self.hr_signature, "signature": self.signature,
            "manifest": self.manifest, "support": self.support, "port_ids": self.port_ids,
            "capacities_liters": self.capacities_liters, "precipitation_mm": self.precipitation_mm,
            "pet_mm": self.pet_mm, "snowfall_mm": self.snowfall_mm, "temperatures_centi_c": self.temperatures_centi_c,
            "year_days": self.year_days, "solution": self.solution.to_dict(),
            "volume_unit": "liter", "unresolved_is_accounting_not_a_mapped_waterbody": True}


def build_water_plan(source, h1, climate, regions=(), hr_config=None, config=None):
    config, hr_config = config or WaterConfig(), hr_config or RegionalHydrologyConfig()
    if (source.config.generator_version != 4 or source.signature != h1.source_signature
            or climate.source_signature != source.signature or climate.hydrology_signature != h1.signature
            or source.config.radius_m != h1.radius_m or climate.radius_m != h1.radius_m
            or source.config.sea_level_m != h1.sea_level_m or climate.sea_level_m != h1.sea_level_m
            or climate.config.climate_version != config.source_climate_version):
        raise ValueError("W1 requires its pinned V4/H1/climate; C1 needs explicit legacy opt-in")
    check_climate_contract(config,climate.config)
    manifest, support, ports = compile_evidence(h1, hr_config, regions)
    g = geometry(h1.config.level)
    keys = ("precipitation_mm", "potential_evapotranspiration_mm", "snowfall_potential_mm", "temperature_centi_c")
    inputs = {key: [[], [], [], []] for key in keys}
    for node, point in enumerate(g.points):
        # H1 stores the authoritative V4 height at this exact same ray.
        sample = sample_climate(climate, point, _terrain_height=h1.heights[node])
        for season in range(4):
            data = hydrology_inputs(sample, season)
            for key in keys:
                inputs[key][season].append(data[key])
    fields = [tuple(tuple(period) for period in inputs[key]) for key in keys]
    capacities = tuple(0 if h1.drainage.marine[i] else h1.cell_area_m2[i]*max(0, h1.drainage.head[i]-h1.heights[i])*1000
                       for i in range(len(h1.heights)))
    directions = tuple(unit(p) for p in g.points)
    distances = tuple(max(1, isqrt(sum((a-b)**2 for a, b in zip(directions[i], directions[parent])))*h1.radius_m//1_000_000)
                      if parent >= 0 else 0 for i, parent in enumerate(h1.drainage.parent))
    solution = solve(h1.cell_area_m2, h1.drainage.marine, h1.drainage.parent, h1.drainage.rank, *fields,
        capacities, tuple(s == "bilateral_downhill_validated" for s in support), distances, climate.config.year_days, config)
    hr_sig = regional_signature(h1, hr_config)
    plan = WaterPlan(config, h1, climate.signature, hr_sig,
        signature(h1.signature, climate.signature, hr_sig, config, manifest), manifest, support, ports,
        capacities, *fields, climate.config.year_days, solution)
    if config.source_climate_version==3:
        from .c3_forcing import attach
        plan=attach(plan,climate)
    validate(plan)
    return plan


def validate(plan):
    h1, count = plan.hydrology, len(plan.hydrology.heights)
    if plan.signature != signature(h1.signature, plan.climate_signature, plan.hr_signature, plan.config, plan.manifest):
        raise ValueError("W1 signature mismatch")
    if plan.config.source_climate_version==3:
        from .c3_forcing import validate_diagnostics
        validate_diagnostics(plan)
    if (len(plan.manifest) > MAX_EVIDENCE_REGIONS or len(set(node for node, _ in plan.manifest)) != len(plan.manifest)
            or tuple(sorted(plan.manifest)) != plan.manifest or any(not 0 <= n < count for n, _ in plan.manifest)):
        raise ValueError("Invalid W1 evidence manifest")
    if any(len(a) != count for a in (plan.support, plan.port_ids, plan.capacities_liters)):
        raise ValueError("Invalid W1 topology budget")
    if any(s not in SUPPORT for s in plan.support) or not 4 <= plan.year_days <= 10000:
        raise ValueError("Invalid W1 routing state/time scale")
    nodes = dict(plan.manifest)
    for i, state in enumerate(plan.support):
        if state == "bilateral_downhill_validated" and (i not in h1.channel_index or i not in nodes
                or h1.drainage.parent[i] not in nodes or not isinstance(plan.port_ids[i], str)):
            raise ValueError("W1 physical transfer requires two pinned HR1 regions")
    for values in (plan.precipitation_mm, plan.pet_mm, plan.snowfall_mm, plan.temperatures_centi_c):
        if len(values) != 4 or any(len(row) != count or any(type(v) is not int for v in row) for row in values):
            raise ValueError("Invalid W1 forcing")
    validate_balance(plan.solution, h1.cell_area_m2, h1.drainage.marine, h1.drainage.parent, h1.drainage.rank, plan.config)
    for season, period in enumerate(plan.solution.periods):
        for i, area in enumerate(h1.cell_area_m2):
            expected = 0 if h1.drainage.marine[i] else area*max(0, h1.drainage.head[i]-h1.heights[i])*1000
            if plan.capacities_liters[i] != expected or period["stores"]["depression"][i] > expected:
                raise ValueError("W1 capacity exceeds its declared H1 column hypothesis")
            for field, forcing in (("precipitation", plan.precipitation_mm), ("pet", plan.pet_mm), ("snowfall", plan.snowfall_mm)):
                amount = 0 if h1.drainage.marine[i] else forcing[season][i]*area
                if period["fluxes"][field][i] != amount:
                    raise ValueError("W1 climate forcing/ledger mismatch")
            if plan.support[i] != "bilateral_downhill_validated" and period["fluxes"]["outflow"][i]:
                raise ValueError("W1 cannot transfer water through unproven geometry")


def load_water_plan(data, h1, climate, hr_signature):
    config = parse_water_config(data["config"])
    if (data.get("kind") != "water_balance_w1" or type(data.get("water_version")) is not int or data["water_version"] != 1
            or data.get("source_signature") != h1.source_signature or data.get("hydrology_signature") != h1.signature
            or data.get("climate_signature") != climate.signature or data.get("hr_signature") != hr_signature
            or config.source_climate_version != climate.config.climate_version or data.get("year_days") != climate.config.year_days):
        raise ValueError("W1 persisted provenance/version mismatch")
    check_climate_contract(config,climate.config)
    saved = data["solution"]
    solution = WaterSolution(tuple(tuple(a) for a in saved["initial_stores"]),
        tuple(freeze_period(p) for p in saved["periods"]), saved["warmup_years"], saved["initial_condition"])
    plan = WaterPlan(config, h1, climate.signature, hr_signature, data["signature"],
        tuple(tuple(pair) for pair in data["manifest"]), tuple(data["support"]), tuple(data["port_ids"]),
        tuple(data["capacities_liters"]), *(tuple(tuple(row) for row in data[name]) for name in
            ("precipitation_mm", "pet_mm", "snowfall_mm", "temperatures_centi_c")), data["year_days"], solution)
    if config.source_climate_version==3:
        from .c3_forcing import load
        plan=load(data,plan,climate)
    validate(plan)
    return plan
