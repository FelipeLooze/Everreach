"""Bounded static geological reconstruction, independent of terrain-query LOD."""
from copy import deepcopy
from dataclasses import dataclass
from .config import GeologyConfig
from .catalog import load_catalog
from ..formation_v4 import cell_area_weight, sample_center, RANDOM_RANGE
from ..formation_noise import unit_direction, dot, noise
from ..formation_config import calibrated_scale
from ..formation_tectonics import evaluate
from ..randomness import coordinate_seed
from ..sphere_topology import SurfacePoint
from ..terrain.field import checksum


def substrate(number):
    return f"EV-GEO-SUB-{number:03d}"


def reconstruct(source, slot, center):
    """New J1 histories, not claims that these records existed in V4."""
    context = evaluate(source.seed, source.config, source.plates, SurfacePoint(*center))
    plate = next(p for p in source.plates if p.slot == context["dominant_plate"])
    scale = calibrated_scale(source.config)
    active = [s for s in context["structures"] if abs(s["boundary_distance_m"]) <= 4*scale["orogen_width_m"]]
    compression = max([0]+[s["closing_micro_mm_year"] for s in active])
    extension = max([0]+[-s["closing_micro_mm_year"] for s in active])
    shear = max([0]+[s["shear_micro_mm_year"] for s in active])
    mechanisms = sorted({s["mechanism"] for s in active})
    direction = tuple(center)
    # Correlated geological fabric, independent of altitude, climate and biomes.
    fabric = noise(source.seed, direction, source.config.radius_m, max(1, scale["plate_length_m"]//3), "J1_basement_fabric")
    basin = noise(source.seed, direction, source.config.radius_m, max(1, scale["plate_length_m"]//2), "J1_ancient_basin")
    arc = bool(set(mechanisms) & {"subduction_arc", "island_arc"}) and compression > 1_000_000
    rift = extension > 1_000_000
    collision = "continental_collision" in mechanisms and compression > 1_000_000
    age = plate.age_myr
    history = [{"kind": "crust_assembly", "age_myr": age, "plate_slot": plate.slot,
                "continental": plate.continental, "rule": "J1 inherited V4 kinematic crust"}]
    base = 1 if plate.continental else (4 if age > 90 else 2)
    if not plate.continental and rift and fabric > 1000:
        base = 5
    if arc:
        base = 3 if fabric < 3500 else 15
    # Ancient depositional package is a J1 history hypothesis; no current wetness implied.
    sediment = plate.continental and basin > -1000 and not arc
    if sediment:
        base = (6, 7, 8, 9, 10)[min(4, max(0, (fabric+10000)*5//20001))]
        history.append({"kind": "ancient_basin_deposition", "age_myr": max(1, age*2//3),
                        "facies_substrate": substrate(base), "basin_field": basin,
                        "rule": "J1 correlated ancient accommodation/facies; not present-day hydrology"})
    precursor = base
    if collision:
        base = {6: 12, 7: 11, 8: 13, 9: 13, 10: 11}.get(base, 14)
        history.append({"kind": "regional_metamorphism", "age_myr": max(1, age//3),
                        "precursor": substrate(precursor), "product": substrate(base),
                        "closing_micro_mm_year": compression})
    intrusion = arc or rift or (plate.continental and not sediment and fabric > 1000)
    thickness = 300+abs(fabric)*2+age*15
    # Geometric burial proxy, independent of altitude. 0..100 remains an access
    # index, not a claim that D14 indices were originally physical metres.
    burial = thickness//3
    depth = max(20, min(95, burial//100))
    fractures = bool(compression > 1_000_000 or extension > 1_000_000 or shear > 1_000_000)
    if intrusion:
        history.append({"kind": "intrusive_thermal_episode", "age_myr": max(1, age//4),
                        "host_substrate": substrate(base), "thickness_m": thickness,
                        "rule": "J1 arc/rift or exposed continental plutonic basement"})
    if fractures:
        history.append({"kind": "fracture_network", "age_myr": max(1, age//5),
                        "closing_micro_mm_year": compression, "extension_micro_mm_year": extension,
                        "shear_micro_mm_year": shear, "mechanisms": mechanisms})
    circulation = intrusion and fractures
    if circulation:
        history.append({"kind": "hydrothermal_circulation", "age_myr": max(1, age//6),
                        "thermal_source": "intrusive_thermal_episode", "permeability_source": "fracture_network",
                        "rule": "J1 ancient magmatic fluid circulation; not C2/W1 recharge"})
    concentration = circulation or (sediment and precursor in (6, 8, 9) and age >= 100)
    evidence = {}
    def add(flag, cause):
        evidence[flag] = {"authority": "J1", "history_kind": cause}
    if sediment:
        add("ambiente_deposicional_confirmado", "ancient_basin_deposition")
    if fractures:
        add("fraturas_mapeadas", "fracture_network")
    if circulation:
        add("circulacao_mineralizante_confirmada", "hydrothermal_circulation")
        add("processo_mineralizante_confirmado", "hydrothermal_circulation")
        if base in (1, 3, 11, 13, 14, 15):
            add("veio_aurifero_primario", "hydrothermal_circulation")
            add("processo_aurifero_profundo", "hydrothermal_circulation")
        add("mineralizacao_argentifera_profunda", "hydrothermal_circulation")
        if arc:
            add("alteracao_hidrotermal_em_unidade_vulcanica", "hydrothermal_circulation")
    if concentration:
        history.append({"kind": "mineral_system_potential", "age_myr": max(1, age//7),
                        "process": "hydrothermal" if circulation else "ancient_diagenetic",
                        "meaning": "modeled favorable concentration; not an instantiated ore deposit"})
        add("concentracao_mineralizante_confirmada", "mineral_system_potential")
    if sediment and precursor in (8, 9) and age >= 100:
        add("horizonte_ferrifero_confirmado", "mineral_system_potential")
    if sediment and precursor == 6 and concentration:
        add("mineralizacao_plumbifera_sedimentar", "mineral_system_potential")
    if arc:
        history.append({"kind": "volcanic_sequence", "age_myr": max(1, age//3), "mechanisms": mechanisms})
        add("historico_vulcanico_persistente", "volcanic_sequence")
    if intrusion and depth >= 60:
        add("unidade_geologica_profunda", "intrusive_thermal_episode")
    return {"substrates": [substrate(base)], "history": history, "evidence_records": evidence,
            "depth_index_0_100": depth, "thickness_m": thickness, "burial_proxy_m": burial,
            "tectonic_source": {"dominant_plate": plate.slot, "plate_age_myr": age,
                "continental_crust_ppm": context["continental_crust_ppm"], "structures": active},
            "terrain_conditioning": False, "present_water_or_ecosystem_inferred": False}


@dataclass(frozen=True)
class GeologyPlan:
    data: dict

    @property
    def signature(self):
        return self.data["signature"]

    @property
    def units(self):
        return self.data["units"]

    def unit_at(self, point):
        if not isinstance(point, SurfacePoint):
            raise ValueError("J1 requires an exact spherical point")
        direction = unit_direction(point)
        index = min(range(len(self.units)), key=lambda i: (-dot(direction, self.units[i]["center"]), self.units[i]["slot"]))
        return deepcopy(self.units[index])

    def to_dict(self):
        return deepcopy(self.data)


def build_geology_plan(terrain, config=None):
    source = terrain.source
    if source.config.generator_version != 4:
        raise ValueError("J1 requires explicit V4/T1")
    config = config or GeologyConfig()
    catalog = load_catalog()
    inputs = {"kind": "geology_j1", "geology_version": 1, "source_signature": source.signature,
              "source_checksum": checksum(source.to_dict()), "terrain_signature": terrain.signature,
              "config": config.model_dump(), "base_sha256": catalog["base_sha256"],
              "extension_sha256": catalog["extension_sha256"], "radius_m": source.config.radius_m}
    sig = checksum(inputs)[:24]
    seed = coordinate_seed(source.seed, 1, "geological_sites_J1")
    weights = [cell_area_weight(i) for i in range(384)]
    slots = [i for i, w in enumerate(weights) if coordinate_seed(seed, 1, "geology_activation", i)*sum(weights) < config.expected_provinces*w*RANDOM_RANGE]
    if len(slots) < 2:
        raise ValueError("J1 geological partition needs at least two sites")
    units = []
    for slot in slots:
        center = sample_center(seed, slot)
        identifier = "geo:"+checksum([sig, slot])[:28]
        region = "geo-region:"+checksum([sig, min(source.plates, key=lambda p: (-dot(p.center, center), p.slot)).slot])[:24]
        units.append({"geological_unit_id": identifier, "formation_opportunity_id": "formation:"+identifier,
                      "geological_region_id": region, "slot": slot, "center": list(center),
                      **reconstruct(source, slot, center)})
    data = {**inputs, "signature": sig, "units": units,
            "partition": "spherical_nearest_site_lowest_slot_tie_no_render_LOD",
            "substrate_status": {s: ("J1_ancient_rock_history" if int(s[-3:]) <= 15 else
                "blocked_requires_fluvial_glacial_evaporative_coastal_or_biological_record") for s in catalog["substrates"]}}
    data["checksum"] = checksum(data)
    return GeologyPlan(data)


def load_geology_plan(data, terrain):
    raw = {k: v for k, v in data.items() if k != "checksum"}
    catalog = load_catalog()
    if (data.get("checksum") != checksum(raw) or type(data.get("geology_version")) is not int or data["geology_version"] != 1 or
            data["source_checksum"] != checksum(terrain.source.to_dict()) or data["terrain_signature"] != terrain.signature or
            data["base_sha256"] != catalog["base_sha256"] or data["extension_sha256"] != catalog["extension_sha256"] or
            not 2 <= len(data["units"]) <= 384):
        raise ValueError("J1 saved authority mismatch; refusing regeneration")
    config = GeologyConfig.model_validate(data["config"])
    inputs = {"kind": "geology_j1", "geology_version": 1, "source_signature": terrain.source.signature,
              "source_checksum": checksum(terrain.source.to_dict()), "terrain_signature": terrain.signature,
              "config": config.model_dump(), "base_sha256": catalog["base_sha256"],
              "extension_sha256": catalog["extension_sha256"], "radius_m": terrain.source.config.radius_m}
    if any(data.get(k) != v for k,v in inputs.items()) or data["signature"] != checksum(inputs)[:24]:
        raise ValueError("J1 pinned input signature mismatch")
    if len({u["slot"] for u in data["units"]}) != len(data["units"]):
        raise ValueError("Duplicate geological bodies")
    for unit in data["units"]:
        if (unit["geological_unit_id"] != "geo:"+checksum([data["signature"],unit["slot"]])[:28] or
                not set(unit["substrates"]) <= set(catalog["substrates"])):
            raise ValueError("Geological body identity/substrate mismatch")
    return GeologyPlan(deepcopy(data))
