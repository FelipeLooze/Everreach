"""Bounded current-event readsets over G1's local closed coverage."""
from sqlalchemy import and_, or_
from sqlalchemy.orm.util import identity_key
from app.db.models.world_hydro_geometry import GenesisHydroGeometryEvidence
from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
from app.db.models.world_terrain import GenesisTerrainTile
from ..hydro_geometry.service import _ranges, _overlaps
from ..terrain.field import checksum


def event_snapshot(db, campaign_id, geometry, limit):
    row = db.get(GenesisHydroGeometryEvidence, (campaign_id, geometry["request_id"]))
    g1_changes = row.changes if row is not None else {"missing": True}
    node = geometry["request"]["provenance"].get("hr1_node")
    hr = db.get(GenesisHydrologyRegion, (campaign_id, node)) if type(node) is int else None
    if hr is not None and hr not in db.dirty and hr not in db.new:
        db.refresh(hr)
    hr_changes = hr.changes if hr is not None else {}
    boxes, predicates = geometry["terrain_coverage"], []
    for box in boxes:
        for level in range(47):
            a, b, c, d = _ranges(box, level)
            predicates.append(and_(GenesisTerrainTile.face == box["face"], GenesisTerrainTile.level == level,
                GenesisTerrainTile.x.between(a, b), GenesisTerrainTile.y.between(c, d)))
    headers = db.query(GenesisTerrainTile.face, GenesisTerrainTile.level, GenesisTerrainTile.x, GenesisTerrainTile.y,
        GenesisTerrainTile.changes).filter(GenesisTerrainTile.campaign_id == campaign_id,
            GenesisTerrainTile.changes != {}, or_(*predicates)).order_by(GenesisTerrainTile.face,
            GenesisTerrainTile.level, GenesisTerrainTile.x, GenesisTerrainTile.y).limit(limit+1).all()
    found = {}
    for face, level, x, y, changes in headers:
        tracked = db.identity_map.get(identity_key(GenesisTerrainTile, (campaign_id, face, level, x, y)))
        current = tracked.changes if tracked is not None and (tracked in db.dirty or tracked in db.new) else changes
        if current:
            found[face, level, x, y] = checksum(current)
    for tracked in db.dirty | db.new:
        if (isinstance(tracked, GenesisTerrainTile) and tracked.campaign_id == campaign_id and
                tracked.changes and _overlaps(tracked, boxes)):
            found[tracked.face, tracked.level, tracked.x, tracked.y] = checksum(tracked.changes)
            if len(found) > limit:
                break
    snapshot = {"g1_changes_checksum": checksum(g1_changes), "hr1_changes_checksum": checksum(hr_changes),
        "g1_events_present": bool(g1_changes), "hr1_events_present": bool(hr_changes),
        "terrain_events": [[*k, v] for k, v in sorted(found.items())[:limit]],
        "event_budget_exceeded": len(found) > limit or len(headers) > limit,
        "event_timestamps": "source_events_preserved_by_hash_observed_at_revision_time"}
    snapshot["current"] = not (g1_changes or hr_changes or found or snapshot["event_budget_exceeded"])
    snapshot["checksum"] = checksum(snapshot)
    return snapshot
