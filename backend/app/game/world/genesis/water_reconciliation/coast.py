"""O1 sampled connection to a named historical ocean reference patch, not export."""
from pydantic import BaseModel, ConfigDict, Field
from ..sphere_topology import SurfacePoint, cell_at
from ..formation_plan import cell_index
from ..terrain.field import checksum


class CoastRequest(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    g1_keys: list[str] = Field(min_length=1, max_length=16)
    route_ids: list[str] = Field(min_length=1, max_length=16)
    reference_point: list[int] = Field(min_length=3, max_length=3)
    reference_component_id: str = Field(min_length=1, max_length=160)


def connection_evidence(request, geometries, statuses, source, water, required_spacing_m, reference_components=()):
    reasons, routes, chain = [], [], []
    if len(request.g1_keys) != len(request.route_ids) or len(set(request.g1_keys)) != len(request.g1_keys):
        raise ValueError("O1 needs an ordered, nonduplicated G1 route chain")
    point = SurfacePoint(*request.reference_point)
    if list(point.xyz) != request.reference_point:
        raise ValueError("O1 needs a canonical reference point")
    component = source.component_at(point)
    if request.reference_component_id not in reference_components:
        reasons.append("ocean_reference_not_explicitly_designated")
    if component.kind != "water_body" or component.id != request.reference_component_id:
        reasons.append("historical_reference_component_unverified")
    marine = cell_index(cell_at(point, water.hydrology.config.level))
    if water.hydrology.heights[marine] >= water.hydrology.sea_level_m:
        reasons.append("reference_not_in_historical_marine_domain")
    datum = source.config.sea_level_m*1000
    previous = None
    for key, route_id in zip(request.g1_keys, request.route_ids):
        geometry = geometries.get(key)
        if geometry is None:
            reasons.append("coastal_geometry_missing")
            continue
        if statuses.get(key) != "current":
            reasons.append("coastal_evidence_events_invalidated")
        route = next((r for r in geometry["routes"] if r["id"] == route_id), None)
        if route is None or not route.get("terrain_profile_mm"):
            reasons.append("coastal_trajectory_missing")
            continue
        anchors = {a["id"]: a for a in geometry["request"]["anchors"]}
        start, end = anchors[route["source_anchor_id"]], anchors[route["outlet_anchor_id"]]
        if previous is not None and (start["id"] != previous["id"] or start["point"] != previous["point"]):
            reasons.append("coastal_chain_bilateral_gap")
        if route.get("max_probe_spacing_mm", 10**30) > required_spacing_m*1000:
            reasons.append("coastal_resolution_pending")
        if any(z > datum for z in route["terrain_profile_mm"]):
            reasons.append("coastal_path_has_T1_land_barrier")
        previous = end
        routes.append(route_id)
        chain.append({"g1_key": key, "checksum": checksum(geometry), "route_id": route_id})
    if previous is None or previous["point"] != request.reference_point:
        reasons.append("coastal_chain_does_not_reach_reference")
    final = geometries.get(request.g1_keys[-1])
    graph = final.get("graph") if final else None
    if final and final["grid_spacing_upper_bound_m"] > required_spacing_m:
        reasons.append("reference_wet_patch_resolution_pending")
    if not graph or any(z >= datum for z in graph["heights_mm"]) or any(edge[2] >= datum for edge in graph["edges"]):
        reasons.append("reference_open_wet_patch_not_verified")
    return {"kind": "ocean_connection_o1", "coast_version": 1, "request": request.model_dump(),
        "status": "pending" if reasons else "sampled_connection_to_reference_verified",
        "reasons": sorted(set(reasons)), "chain": chain, "datum_mm": datum,
        "scope": "sampled_wet_path_to_named_reference_patch_not_entire_historical_component",
        "reference_component_id": component.id, "export_authorized": False,
        "hydraulic_capacity_checked_separately": True, "water_ledger_modified": False}
