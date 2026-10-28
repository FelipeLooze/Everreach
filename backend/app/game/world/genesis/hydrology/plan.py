"""H1 compact, immutable macro plan and derived potential river hierarchy."""
from dataclasses import asdict, dataclass, fields
from functools import cached_property
import hashlib
import json
from types import MappingProxyType

from ..formation_plan import FormationPlan
from ..formation_tectonics import evaluate
from ..sphere_topology import SurfacePoint
from .config import HydrologyConfig
from .drainage import Drainage, solve, validate
from .geometry import AREA_UNIT, geometry


def signature(source_signature: str, config: HydrologyConfig) -> str:
    text = json.dumps(["hydrology-h1", source_signature, config.model_dump()], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:24]


@dataclass(frozen=True)
class Reach:
    start: int
    end: int
    nodes: tuple[int, ...]
    area_m2: int
    order: int


@dataclass(frozen=True)
class HydrologyPlan:
    config: HydrologyConfig
    source_signature: str
    radius_m: int
    sea_level_m: int
    signature: str
    heights: tuple[int, ...]
    profiles: tuple[tuple[int, ...], ...]
    cell_area_m2: tuple[int, ...]
    drainage: Drainage

    def identifier(self, kind: str, index: int) -> str:
        return f"hydro-h1:{self.signature}:{kind}:{index}"

    @cached_property
    def channel_threshold_m2(self) -> int:
        return max(1, sum(self.cell_area_m2)*self.config.channel_min_area_ppm//1_000_000)

    @cached_property
    def major_threshold_m2(self) -> int:
        return max(1, sum(self.cell_area_m2)*self.config.major_channel_area_ppm//1_000_000)

    @cached_property
    def reaches(self) -> tuple[Reach, ...]:
        d = self.drainage
        threshold = self.channel_threshold_m2
        channels = {i for i, p in enumerate(d.parent) if p >= 0 and not d.marine[i] and d.area[i] >= threshold}
        incoming = [0]*len(self.heights)
        for i in channels:
            incoming[d.parent[i]] += 1
        result = []
        for start in sorted(channels):
            if incoming[start] == 1:
                continue
            path = [start]
            current = start
            while d.parent[current] >= 0:
                parent = d.parent[current]
                path.append(parent)
                if parent not in channels or incoming[parent] != 1:
                    break
                current = parent
            result.append(Reach(start, path[-1], tuple(path), d.area[path[-2]], d.order[path[-2]]))
        return tuple(result)

    @cached_property
    def channel_index(self):
        return MappingProxyType({node: ordinal for ordinal, reach in enumerate(self.reaches) for node in reach.nodes[:-1]})

    @cached_property
    def pool_index(self):
        return MappingProxyType({node: ordinal for ordinal, pool in enumerate(self.drainage.depressions) for node in pool})

    def edge_record(self, source: int) -> dict:
        d = self.drainage
        target = d.parent[source]
        if target < 0:
            raise ValueError("A terminal has no outgoing edge")
        g = geometry(self.config.level)
        index = g.edge_lookup[tuple(sorted((source, target)))]
        raw = self.profiles[index] if source < target else self.profiles[index][::-1]
        # Downstream suffix envelope, never below sampled bed and never uphill.
        heads = [d.head[target]]*len(raw)
        for i in range(len(raw)-1, -1, -1):
            heads[i] = max(raw[i], heads[i+1] if i+1 < len(raw) else d.head[target])
        if heads[0] != d.head[source]:
            raise ValueError("Edge does not match conditioned source head")
        return {"id": self.identifier("edge", index), "edge_index": index, "source": source, "target": target,
            "port": list(g.ports[index].xyz), "sampled_terrain_m": list(raw), "potential_head_profile_m": heads,
            "raise_above_sampled_terrain_m": [h-z for h, z in zip(heads, raw)],
            "requires_storage_head_at_source": d.head[source] > self.heights[source],
            "contributing_area_m2": d.area[source], "potential_strahler_order": d.order[source],
            "water_availability": "unknown", "discharge_m3_s": None, "perennial": None}

    def network_records(self) -> list[dict]:
        incoming = {}
        for reach in self.reaches:
            incoming.setdefault(reach.end, []).append(self.identifier("reach", reach.start))
        d = self.drainage
        return [{"id": self.identifier("reach", r.start), "start": r.start, "end": r.end, "nodes": list(r.nodes),
            "contributing_area_m2": r.area_m2, "potential_strahler_order": r.order,
            "major_potential_channel": r.area_m2 >= self.major_threshold_m2,
            "upstream_reach_ids": sorted(incoming.get(r.start, [])),
            "basin_id": self.identifier("basin", d.outlet[r.start]),
            "outlet_type": "reference_ocean" if d.marine[d.outlet[r.start]] else "closed_planet_sink",
            "requires_storage_somewhere": any(any(self.edge_record(n)["raise_above_sampled_terrain_m"])
                                               for n in r.nodes[:-1]),
            "water_availability": "unknown", "discharge_m3_s": None, "perennial": None}
            for r in self.reaches]

    def basin_records(self) -> list[dict]:
        d = self.drainage
        roots = sorted({d.outlet[i] for i in range(len(self.heights)) if not d.marine[i]})
        return [{"id": self.identifier("basin", root), "outlet_node": root, "contributing_area_m2": d.area[root],
                 "outlet_type": "reference_ocean" if d.marine[root] else "closed_planet_sink"} for root in roots]

    def divide_records(self) -> list[dict]:
        d, g = self.drainage, geometry(self.config.level)
        return [{"id": self.identifier("divide", index), "between_basins": sorted((
                    self.identifier("basin", d.outlet[a]), self.identifier("basin", d.outlet[b]))),
                 "representative_point": list(g.ports[index].xyz), "status": "macro_divide_candidate"}
                for index, (a, b) in enumerate(g.edges)
                if not d.marine[a] and not d.marine[b] and d.outlet[a] != d.outlet[b]]

    def closed_basin_records(self) -> list[dict]:
        d = self.drainage
        roots = sorted({d.raw_outlet[i] for i in range(len(self.heights)) if not d.marine[i]})
        return [{"id": self.identifier("closed-basin", root), "bottom_node": root,
            "unconditioned_contributing_area_m2": d.raw_area[root],
            "bottom_elevation_m": self.heights[root],
            "potential_overflow_elevation_m": d.head[root] if d.parent[root] >= 0 else None,
            "potential_receiving_basin_id": self.identifier("basin", d.outlet[root]),
            "state": "endorheic_candidate_until_storage_and_water_balance_are_known"}
            for root in roots if not d.marine[root]]

    def lake_records(self) -> list[dict]:
        d, g = self.drainage, geometry(self.config.level)
        result = []
        for ordinal, pool in enumerate(d.depressions):
            members = set(pool)
            chosen = sorted((i, d.parent[i]) for i in pool if d.parent[i] not in members and d.parent[i] >= 0)
            alternatives = sorted({edge for i in pool for other, edge in g.adjacency[i]
                if other not in members and max(self.profiles[edge]) <= d.head[pool[0]] and d.head[other] <= d.head[pool[0]]})
            result.append({"id": self.identifier("lake-candidate", pool[0]), "nodes": list(pool),
                "spill_elevation_m": d.head[pool[0]], "floor_min_m": min(self.heights[i] for i in pool),
                "sampled_storage_area_m2": sum(self.cell_area_m2[i] for i in pool),
                "selected_spill_edges": [self.identifier("edge", g.edge_lookup[tuple(sorted(pair))]) for pair in chosen],
                "possible_spill_edges": [self.identifier("edge", edge) for edge in alternatives],
                "volume_available_m3": None, "permanent": None,
                "state": "depression_storage_potential_not_a_filled_lake"})
        return result

    def water_records(self) -> list[dict]:
        d = self.drainage
        return [{"id": self.identifier("below-datum-body", group[0]), "nodes": list(group),
            "connected_to_reference_ocean": d.marine[group[0]],
            "state": "marine_reservoir_boundary_assumption" if d.marine[group[0]] else "disconnected_below_datum",
            "permanent_interior_water": None} for group in d.water_components]

    def to_dict(self) -> dict:
        return {"kind": "macro_hydrology_h1", "config": self.config.model_dump(),
            "source_signature": self.source_signature, "radius_m": self.radius_m, "sea_level_m": self.sea_level_m,
            "signature": self.signature, "heights": list(self.heights), "profiles": [list(p) for p in self.profiles],
            "cell_area_m2": list(self.cell_area_m2), "drainage": asdict(self.drainage),
            "water_balance": "not_modeled", "geometry_status": "macro_potential_requires_regional_refinement"}


def build_hydrology_plan(source: FormationPlan, config: HydrologyConfig | None = None) -> HydrologyPlan:
    if source.config.generator_version != 4:
        raise ValueError("H1 requires an explicitly pinned V4 world; no legacy conversion")
    config = config or HydrologyConfig()
    g = geometry(config.level)
    sampled = {}
    def height(point: SurfacePoint) -> int:
        if point not in sampled:
            sampled[point] = evaluate(source.seed, source.config, source.plates, point, causes=False)["elevation_m"]
        return sampled[point]
    heights = tuple(height(p) for p in g.points)
    profiles = tuple(tuple(height(p) for p in profile) for profile in g.profiles)
    cell_area = tuple(weight*source.config.radius_m**2//AREA_UNIT for weight in g.area_units)
    solution = solve(heights, g.edges, tuple(max(p) for p in profiles), cell_area, source.config.sea_level_m)
    return HydrologyPlan(config, source.signature, source.config.radius_m, source.config.sea_level_m,
                         signature(source.signature, config), heights, profiles, cell_area, solution)


def load_hydrology_plan(data: dict, source_signature: str, radius_m: int, sea_level_m: int) -> HydrologyPlan:
    config = HydrologyConfig.model_validate(data["config"])
    if (data.get("kind") != "macro_hydrology_h1" or data.get("source_signature") != source_signature or
        data.get("radius_m") != radius_m or data.get("sea_level_m") != sea_level_m or
        data.get("signature") != signature(source_signature, config)):
        raise ValueError("Hydrology source/version/signature mismatch")
    g = geometry(config.level)
    heights, profiles, area = tuple(data["heights"]), tuple(tuple(p) for p in data["profiles"]), tuple(data["cell_area_m2"])
    if (len(heights) != len(g.points) or len(profiles) != len(g.edges) or len(area) != len(g.points)
            or any(len(p) != 5 for p in profiles) or any(type(z) is not int for z in heights)
            or any(type(a) is not int or a <= 0 for a in area)):
        raise ValueError("Invalid hydrology sampling budget/data")
    for (a, b), profile in zip(g.edges, profiles):
        if profile[0] != heights[a] or profile[-1] != heights[b] or any(type(z) is not int for z in profile):
            raise ValueError("Profile is inconsistent with shared terrain samples")
    values = data["drainage"]
    nested = {"water_components", "depressions"}
    drainage = Drainage(**{field.name: tuple(tuple(group) for group in values[field.name]) if field.name in nested
                           else tuple(values[field.name]) for field in fields(Drainage)})
    validate(drainage, heights, g.edges, tuple(max(p) for p in profiles), area, sea_level_m)
    return HydrologyPlan(config, source_signature, radius_m, sea_level_m, data["signature"], heights, profiles, area, drainage)
