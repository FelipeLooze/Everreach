"""Physical W2 admission policy version 1. Unknown G1 capacity is NOT approval."""
from ..formation_plan import cell_index
from ..sphere_topology import CellKey
from ..terrain.address import TerrainTile
from ..hydro_geometry.regional import compare_boundaries


def domain_of(geometry, h1_level):
    tile = TerrainTile(*geometry["request"]["tile"])
    p = tile.parent(h1_level)
    return cell_index(CellKey(p.face, p.level, p.x, p.y))


def assess_geometry(geometry, required_spacing_m):
    reasons = []
    if geometry["status"] != "sampled_geometry_prepared":
        reasons.append("geometry_preparation_pending")
    if not geometry["routes"]:
        reasons.append("trajectory_missing")
    for route in geometry["routes"]:
        if route["status"] != "verified_at_requested_resolution":
            reasons.append(route["status"])
        if route.get("max_probe_spacing_mm", 10**30) > required_spacing_m*1000:
            reasons.append("required_resolution_pending")
        if any(route.get("storage_raise_mm", [])) or route.get("storage_evidence", {}).get("subedge_storage_unresolved"):
            reasons.append("storage_and_spill_reconciliation_pending")
        if route.get("endpoint_head_violations") or route.get("path_excess_above_source_reference_mm", 0):
            reasons.append("legacy_heads_incompatible")
    sections = geometry["sections"]
    if not sections:
        reasons.append("sections_missing")
    if any(s["status"] != "sampled_banked_section" for s in sections):
        reasons.append("open_or_unconfined_section")
    # G1 v1 has no authenticated whole-route hydraulic-capacity certificate.
    # A finite number injected into an old JSON field is not a new proof policy.
    reasons.append("hydraulic_capacity_not_proved_by_G1_v1")
    if geometry["coast"] and geometry["coast"]["legacy_t1_disagreements"]:
        reasons.append("coastal_classification_requires_T1_connection_evidence")
    return {"policy_version": 1, "status": "pending", "reasons": sorted(set(reasons)),
            "capacity_liters": None, "geometry_only": True, "physical_impossibility_claimed": False}


def assess_transfer(intent, geometries, statuses, water, config, coast=None):
    reasons, proof_domains = [], set()
    for key in intent.evidence_keys:
        if key not in geometries:
            reasons.append("geometry_evidence_missing")
            continue
        geometry = geometries[key]
        proof_domains.add(domain_of(geometry, water.hydrology.config.level))
        reasons.extend(assess_geometry(geometry, config.required_probe_spacing_m)["reasons"])
        if statuses.get(key) != "current":
            reasons.append("geometry_events_or_provenance_invalidated")
    if intent.source_node not in proof_domains:
        reasons.append("source_geometry_missing")
    if intent.target_node is not None and intent.target_node not in proof_domains:
        reasons.append("target_geometry_missing")
    if intent.target_node is not None and intent.source_node != intent.target_node and water.hydrology.drainage.parent[intent.source_node] != intent.target_node:
        reasons.append("not_an_existing_H1_receiver_boundary")
    values = [geometries[k] for k in intent.evidence_keys if k in geometries]
    bilateral = [compare_boundaries(a, b) for i, a in enumerate(values) for b in values[i+1:]]
    if not any(p["status"] == "bilateral_sampled_geometry_verified" for p in bilateral):
        reasons.append("bilateral_continuity_pending")
    if intent.target_node is None:
        if coast is None or coast.get("status") != "sampled_connection_to_reference_verified":
            reasons.append("ocean_reference_connection_pending")
    return {"policy_version": 1, "status": "pending", "reasons": sorted(set(reasons)),
        "capacity_liters": None, "capacity_key": None, "bilateral": bilateral,
        "ocean_export_authorized": False, "physical_impossibility_claimed": False}
