from .formation_plan import FormationPlan
from .formation_tectonics import evaluate
from .sphere_topology import CellKey, SurfacePoint, face_point


def sample_at(plan: FormationPlan, point: SurfacePoint) -> dict:
    result = evaluate(plan.seed, plan.config, plan.plates, point)
    component = plan.component_at(point)
    local_land = result["elevation_m"] >= plan.config.sea_level_m
    agrees = local_land == (component.kind == "landmass")
    result["identity"] = {"macro_component_id": component.id,
                          "guarantee": "macro_cell_center_connectivity", "identity_level": plan.config.macro_level,
                          "macro_kind": component.kind, "local_kind": "land" if local_land else "water",
                          "resolution_mismatch": not agrees,
                          "physical_component_id": component.id if agrees else None}
    result["plate_id"] = f"plate:{plan.signature}:{result['dominant_plate']}"
    for structure in result["structures"]:
        a, b = structure["plates"]
        structure["id"] = f"{structure['mechanism']}:{plan.signature}:{a}:{b}"
    return result


def generate_sector(plan: FormationPlan, key: CellKey) -> dict:
    config = plan.config
    if key.level != config.sector_level:
        raise ValueError("Materialization requires the pinned sector level")
    intervals = config.sample_intervals
    geology = [[sample_at(plan, face_point(key.face, key.x*intervals+x, key.y*intervals+y,
                                          2**key.level*intervals)) for x in range(intervals+1)]
                                          for y in range(intervals+1)]
    return {"generator_version": config.generator_version, "plan_signature": plan.signature,
            "cell": [key.face, key.level, key.x, key.y], "sample_intervals": intervals,
            "sea_level_m": config.sea_level_m, "elevation_m": [[s["elevation_m"] for s in row] for row in geology],
            "geology": geology}
