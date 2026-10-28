"""Bounded global macro components, built before any sector materialization."""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json

from .formation_config import FormationConfig, calibrated_scale
from .formation_plates import MAX_PLATES, Plate, nucleate_plates
from .formation_tectonics import evaluate
from .sphere_topology import CellKey, DIRECTIONS, SurfacePoint, cell_at, cell_center, neighbor


@dataclass(frozen=True)
class PhysicalComponent:
    id: str
    kind: str
    anchor_index: int
    cell_count: int


@dataclass(frozen=True)
class FormationPlan:
    seed: int
    config: FormationConfig
    signature: str
    plates: tuple[Plate, ...]
    labels: tuple[int, ...]
    components: tuple[PhysicalComponent, ...]

    def component_at(self, point: SurfacePoint) -> PhysicalComponent:
        key = cell_at(point, self.config.macro_level)
        return self.components[self.labels[cell_index(key)]]

    def to_dict(self) -> dict:
        return {"kind": f"plate_formation_v{self.config.generator_version}", "seed": self.seed,
                "config": self.config.model_dump(mode="json"), "signature": self.signature,
                "scale": calibrated_scale(self.config), "plates": [p.to_dict() for p in self.plates],
                "labels": list(self.labels), "components": [vars(c).copy() for c in self.components]}


def cell_index(key: CellKey) -> int:
    n = 2**key.level
    return key.face*n*n+key.y*n+key.x


def indexed_cell(index: int, level: int) -> CellKey:
    n = 2**level
    face, local = divmod(index, n*n)
    y, x = divmod(local, n)
    return CellKey(face, level, x, y)


def _signature(seed: int, config: FormationConfig) -> str:
    value = json.dumps([seed, config.model_dump(mode="json")], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def identify_components(seed: int, config: FormationConfig, land: tuple[bool, ...]) -> tuple[tuple[int, ...], tuple[PhysicalComponent, ...]]:
    count = 6*4**config.macro_level
    if len(land) != count or any(type(value) is not bool for value in land):
        raise ValueError("Expected one boolean classification per macro cell")
    labels = [-1]*count
    components = []
    signature = _signature(seed, config)
    for anchor in range(count):
        if labels[anchor] != -1:
            continue
        label = len(components)
        labels[anchor] = label
        pending = [anchor]
        size = 0
        while pending:
            index = pending.pop()
            size += 1
            key = indexed_cell(index, config.macro_level)
            for direction in DIRECTIONS:
                adjacent = cell_index(neighbor(key, direction))
                if labels[adjacent] == -1 and land[adjacent] == land[anchor]:
                    labels[adjacent] = label
                    pending.append(adjacent)
        kind = "landmass" if land[anchor] else "water_body"
        components.append(PhysicalComponent(f"{kind}:{signature}:{anchor}", kind, anchor, size))
    return tuple(labels), tuple(components)


@lru_cache(maxsize=2)
def build_plan(seed: int, config: FormationConfig) -> FormationPlan:
    if config.generator_version == 4:
        from .formation_v4 import nucleate_plates_v4
        plates = nucleate_plates_v4(seed, config)
    else:
        plates = nucleate_plates(seed, config)
    count = 6*4**config.macro_level
    land = tuple(evaluate(seed, config, plates, cell_center(indexed_cell(i, config.macro_level)),
                          causes=False)["elevation_m"] >= config.sea_level_m for i in range(count))
    labels, components = identify_components(seed, config, land)
    return FormationPlan(seed, config, _signature(seed, config), plates, labels, components)


def load_plan(data: dict, seed: int, config: FormationConfig) -> FormationPlan:
    """Load the persisted authority; never rebuild a saved plan while loading."""
    if (data.get("kind") != f"plate_formation_v{config.generator_version}" or data.get("seed") != seed or
            data.get("config") != config.model_dump(mode="json") or data.get("signature") != _signature(seed, config)):
        raise ValueError("Formation plan does not match its pinned seed/configuration")
    count = 6*4**config.macro_level
    if not 2 <= len(data["plates"]) <= MAX_PLATES or len(data["labels"]) != count:
        raise ValueError("Invalid formation plan budget")
    components = tuple(PhysicalComponent(**c) for c in data["components"])
    labels = tuple(data["labels"])
    if (not 1 <= len(components) <= count or any(type(i) is not int or not 0 <= i < len(components) for i in labels)
            or sum(c.cell_count for c in components) != count):
        raise ValueError("Invalid component index")
    plates = tuple(Plate(p["slot"], tuple(p["center"]), tuple(p["axis"]), p["continental"],
                         p["age_myr"], p["speed_mm_year"]) for p in data["plates"])
    return FormationPlan(seed, config, data["signature"], plates, labels, components)
