"""Read-only input contract for future W2. No allocation or ledger changes."""
from ..terrain.field import checksum
from ..formation_plan import cell_index
from ..terrain.address import TerrainTile
from ..water.query import node_record
from .regional import compare_boundaries


def water_evidence(geometry, water=None, peers=()):
    # Geometry can be prepared without water. Joining quantities never changes
    # the request ID or opens a route in W1's fixed evidence manifest.
    route_statuses = [r["status"] for r in geometry["routes"]]
    macro = None
    if water is not None:
        tile = TerrainTile(*geometry["request"]["tile"])
        h1 = water.hydrology
        if (geometry["hydrology_signature"] != h1.signature or geometry["hydrology_checksum"] != checksum(h1.to_dict()) or
                geometry["hr_signature"] != water.hr_signature):
            raise ValueError("G1/W1 source authority mismatch")
        provenance = geometry["request"]["provenance"]
        if "hr1_signature" in provenance and provenance["hr1_signature"] != water.hr_signature:
            raise ValueError("G1/W1 HR1 source mismatch")
        if tile.level < h1.config.level:
            raise ValueError("W1 context requires one canonical H1 cell")
        p = tile.parent(h1.config.level)
        from ..sphere_topology import CellKey
        macro = node_record(water, cell_index(CellKey(p.face, p.level, p.x, p.y)))
    return {"kind": "g1_w2_evidence_contract", "contract_version": 1,
        "g1_request_id": geometry["request_id"], "g1_evidence_checksum": checksum(geometry),
        "terrain_signature": geometry["terrain_signature"], "source_geometry_status": geometry["status"],
        "route_statuses": route_statuses, "bilateral": [compare_boundaries(geometry, p) for p in peers],
        "longitudinal_geometry_available": bool(geometry["segments"]), "sections": geometry["sections"],
        "storage_geometry": geometry["depression_geometry"], "coast": geometry["coast"],
        "potential_overflow_locations": geometry["potential_overflow_locations"],
        "w1_signature": water.signature if water else None,
        "w1_manifest_checksum": checksum(water.manifest) if water else None,
        "w1_macro_reference": macro, "quantity_semantics": "macro_reference_not_allocated_to_any_G1_path",
        "water_allocation_liters": None, "pending_water_reconciled": False, "w1_manifest_extended": False,
        "water_ledger_modified": False, "active_river_authorized": False,
        "remaining_checks": ["event_epoch", "bilateral_routes", "subgrid_passages", "legacy_internal_head_reconciliation", "storage_and_spill_connectivity",
                             "hydraulic_conveyance", "W2_conservative_volume_and_time_reconciliation"]}
