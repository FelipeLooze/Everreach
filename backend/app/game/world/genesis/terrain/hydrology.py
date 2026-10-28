"""Read-only T1 compatibility evidence; NEVER changes H1/HR1/W1 or carves a bed."""
from ..coast_refinement import _between
from ..hydrology.regional import validate_region
from ..water.plan import checksum


def audit_regional_constraints(sampler, h1, region, water=None):
    validate_region(region)
    plan = sampler.plan
    if (h1.source_signature != plan.source.signature or region["source_signature"] != plan.source.signature or
            region["hydrology_signature"] != h1.signature or h1.radius_m != plan.source.config.radius_m):
        raise ValueError("T1 hydro evidence source mismatch")
    if water is not None and (water.hydrology.signature != h1.signature or
            water.hydrology.to_dict() != h1.to_dict()):
        raise ValueError("T1 W1/H1 evidence mismatch")
    count = 5*len(region["segments"])+len(region["ports"])+1
    if count > plan.config.max_hydro_samples:
        raise ValueError("T1 hydrology inspection budget exceeded")
    from ..sphere_topology import SurfacePoint
    checks = []
    for segment in region["segments"]:
        a, b = (SurfacePoint(*p) for p in segment["points"])
        heights = [sampler.sample(_between(a, b, i, 4))["height_mm"] for i in range(5)]
        heads = [h*1000 for h in segment["potential_head_profile_m"]]
        excess = max(max(0, z-h) for z, h in zip(heights, heads))
        checks.append({"hr1_segment_id": segment["id"], "height_profile_mm": heights,
            "reference_head_profile_mm": heads, "max_head_exceedance_mm": excess,
            "status": "terrain_exceeds_legacy_head" if excess else "sampled_below_legacy_head",
            "sampled_uphill_mm": max(0, max(b-a for a, b in zip(heights, heights[1:]))),
            "connected_bathymetry": None, "conveyance_capacity": None, "bed_validated": False})
    ports = []
    for port in region["ports"]:
        z = sampler.sample(SurfacePoint(*port["point"]))["height_mm"]
        ports.append({"hr1_port_id": port["id"], "point": port["point"], "height_mm": z,
            "legacy_terrain_mm": port["terrain_m"]*1000, "legacy_head_mm": port["potential_head_m"]*1000,
            "head_exceedance_mm": max(0, z-port["potential_head_m"]*1000)})
    pinned = water is not None and dict(water.manifest).get(region["node"]) == checksum(region)
    from ..water.query import node_record
    return {"kind": "terrain_hydro_constraints_t1", "terrain_signature": plan.signature,
            "hr1_signature": region["signature"], "hr1_checksum": checksum(region), "node": region["node"],
            "water_signature": water.signature if water else None, "in_w1_fixed_manifest": pinned,
            "water_context": node_record(water, region["node"]) if water else None,
            "segments": checks, "ports": ports, "sample_count_upper_bound": count,
            "incompatibility_count": sum(s["max_head_exceedance_mm"] > 0 for s in checks),
            "storage_capacity_liters": None, "permanent_waterbody": None, "water_ledger_modified": False,
            "terrain_baseline_only": True, "terrain_modifications_applied": False,
            "resolution": "requires_explicit_terrain_hydrology_revision_or_conservative_overlay",
            "guarantee": "five_probes_per_legacy_segment_not_continuous_route_validation"}
