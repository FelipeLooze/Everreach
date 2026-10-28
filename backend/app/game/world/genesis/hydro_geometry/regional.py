"""Versioned G1 requests derived from immutable HR1 contracts, not rewrites."""
from ..hydrology.regional import validate_region
from ..sphere_topology import SurfacePoint, DIRECTIONS
from ..terrain.address import TerrainTile, chart
from ..terrain.field import checksum
from .config import Anchor, GeometryRequest
from .graph import SampleContext
from .spatial import edge_points, tile_neighbor


def regional_request(plan, sampler, region, *, candidate_ports=False, grid_intervals=8,
                     target_spacing_m=100, sample_budget=8192, expansion_budget=4096):
    validate_region(region)
    if (region["signature"] != plan.hr_signature or region["source_signature"] != plan.terrain.source.signature or
            region["hydrology_signature"] != plan.hydrology.signature):
        raise ValueError("G1 regional request does not match pinned HR1")
    tile = TerrainTile(*region["tile"])
    context = SampleContext(sampler, min(sample_budget, plan.config.max_samples))
    anchors, proposals = [], []
    outgoing = next((p for p in region["ports"] if p["source_node"] == region["node"]), None)
    for port in region["ports"]:
        old = SurfacePoint(*port["point"])
        point, identifier = old, port["id"]
        if candidate_ports:
            _, u, v, d = chart(old, tile.face)
            scale = 2**tile.level
            side = next((side for side, value in (("west", u*scale-tile.x*d),
                ("east", (tile.x+1)*d-u*scale), ("south", v*scale-tile.y*d),
                ("north", (tile.y+1)*d-v*scale)) if value == 0), None)
            if side is None:
                raise ValueError("HR1 port is not on the regional boundary")
            candidates = edge_points(tile, side, grid_intervals)
            point = min(candidates, key=lambda p: (context.height(p), p.xyz))
            peer = tile_neighbor(tile, side)
            pair = sorted([list(vars(tile).values()), list(vars(peer).values())])
            identifier = f"g1-port:{plan.signature}:{checksum([pair, list(point.xyz), grid_intervals])[:24]}"
            proposals.append({"legacy_port_id": port["id"], "g1_port_id": identifier,
                "legacy_point": port["point"], "g1_point": list(point.xyz),
                "terrain_height_mm": context.height(point), "candidate_count": len(candidates),
                "selection": "lowest_T1_boundary_probe_not_proof_of_complete_bilateral_route"})
        anchors.append(Anchor(id=identifier, point=list(point.xyz), role="outlet" if port is outgoing else "ingress",
                              reference_head_mm=port["potential_head_m"]*1000))
    junction = region["junction"]
    anchors.append(Anchor(id=junction["id"], point=junction["point"], role="relay" if outgoing else "outlet",
                          reference_head_mm=junction["potential_head_m"]*1000))
    if not outgoing and not any(a.role == "ingress" for a in anchors):
        # No spring or corridor invented; the terminal can still have depression evidence.
        pass
    return GeometryRequest(tile=region["tile"], anchors=anchors, grid_intervals=grid_intervals,
        target_spacing_m=target_spacing_m, sample_budget=sample_budget, expansion_budget=expansion_budget,
        origin="hr1_t1_candidates" if candidate_ports else "hr1_legacy",
        provenance={"hr1_node": region["node"], "hr1_signature": region["signature"], "hr1_checksum": checksum(region),
            "h1_junction_id": junction["id"], "h1_storage_candidate_id": region["h1_storage_candidate_id"],
            "hr1_depression_candidate_ids": [c["id"] for c in region["depression_candidates"]],
            "port_proposals": proposals, "port_search_samples": len(context.samples)})


def compare_boundaries(left, right):
    if right is None:
        return {"kind": "g1_bilateral_comparison", "left": left["request_id"], "right": None,
                "status": "neighbor_evidence_pending", "shared_boundaries": [], "physical_blockage_proved": False,
                "water_ledger_modified": False}
    if left["signature"] != right["signature"] or left["terrain_signature"] != right["terrain_signature"]:
        raise ValueError("Cannot compare different G1/T1 authorities")
    a = {v["id"]: v for v in left["request"]["anchors"]}
    b = {v["id"]: v for v in right["request"]["anchors"]}
    records = []
    for identifier in sorted(a.keys() & b.keys()):
        x, y = a[identifier], b[identifier]
        if x["point"] != y["point"] or x["reference_head_mm"] != y["reference_head_mm"]:
            records.append({"id": identifier, "status": "incompatible_shared_contract"})
            continue
        if set((x["role"], y["role"])) != {"ingress", "outlet"}:
            continue
        downstream = right if y["role"] == "ingress" else left
        upstream = left if x["role"] == "outlet" else right
        ingress_routes = [r for r in downstream["routes"] if r["source_anchor_id"] == identifier]
        egress_routes = [r for r in upstream["routes"] if r["outlet_anchor_id"] == identifier]
        routes = ingress_routes+egress_routes
        records.append({"id": identifier, "point": x["point"],
            "status": "bilateral_sampled_geometry_verified" if ingress_routes and egress_routes and
                all(r["status"] == "verified_at_requested_resolution" for r in routes) else "shared_endpoint_only_routes_pending",
            "route_statuses": [r["status"] for r in routes], "active_water_transfer": False})
    return {"kind": "g1_bilateral_comparison", "left": left["request_id"], "right": right["request_id"],
            "status": "no_shared_contract_pending" if not records else
                "incompatible_shared_contract" if any(r["status"] == "incompatible_shared_contract" for r in records) else
                "bilateral_sampled_geometry_verified" if all(r["status"] == "bilateral_sampled_geometry_verified" for r in records) else "partial_or_pending",
            "physical_blockage_proved": False,
            "shared_boundaries": records, "water_ledger_modified": False}


def boundary_probe_request(plan, sampler, tile, outlet_side, ingress_sides, *, grid_intervals=8,
                           target_spacing_m=2, sample_budget=8192, expansion_budget=4096):
    """Explicit local passage probes, not a global drainage receiver assignment.

    A parent proof's anchor must be inherited verbatim in GeometryRequest;
    selecting a new minimum here is an explicit NEW boundary contract.
    """
    if outlet_side not in DIRECTIONS or any(s not in DIRECTIONS or s == outlet_side for s in ingress_sides):
        raise ValueError("Invalid G1 boundary-probe directions")
    if len(set(ingress_sides)) != len(ingress_sides):
        raise ValueError("Duplicate G1 ingress side")
    context = SampleContext(sampler, min(sample_budget, plan.config.max_samples))
    anchors = []
    for side in sorted([outlet_side, *ingress_sides]):
        point = min(edge_points(tile, side, grid_intervals), key=lambda p: (context.height(p), p.xyz))
        peer = tile_neighbor(tile, side)
        pair = sorted([list(vars(tile).values()), list(vars(peer).values())])
        identifier = f"g1-port:{plan.signature}:{checksum([pair, list(point.xyz), grid_intervals])[:24]}"
        anchors.append(Anchor(id=identifier, point=list(point.xyz), role="outlet" if side == outlet_side else "ingress"))
    return GeometryRequest(tile=list(vars(tile).values()), anchors=anchors, grid_intervals=grid_intervals,
        target_spacing_m=target_spacing_m, sample_budget=sample_budget, expansion_budget=expansion_budget,
        provenance={"boundary_probe_only": True, "global_receiver_assigned": False,
                    "port_search_samples": len(context.samples)})
