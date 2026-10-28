"""G1 preparation is explicit; caller owns commit/rollback. No W1 mutation."""
from collections import OrderedDict
from fractions import Fraction
from threading import RLock
from sqlalchemy import and_, or_
from sqlalchemy.orm.util import identity_key
from app.db.models.world_terrain import GenesisTerrainTile
from app.db.models.world_hydro_geometry import GenesisHydroGeometryPlan, GenesisHydroGeometryEvidence
from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
from ..terrain.service import get_terrain_sampler
from ..terrain.address import TerrainTile
from ..terrain.field import checksum
from ..hydrology.service import _header as h1_header, get_hydrology_plan
from ..hydrology.regional_service import _header as hr_header, materialize_hydrology_region
from .config import G1Config, GeometryRequest
from .plan import build_geometry_plan, signature_for
from .geometry import build_geometry, validate_geometry, request_id
from .regional import regional_request
from .spatial import coverage_boxes

_cache, _lock = OrderedDict(), RLock()


def clear_geometry_cache():
    with _lock:
        _cache.clear()


def geometry_cache_size():
    with _lock:
        return len(_cache)


def initialize_geometry(db, campaign_id, config=None):
    sampler = get_terrain_sampler(db, campaign_id)
    hr, _, _ = hr_header(db, campaign_id)
    row = db.get(GenesisHydroGeometryPlan, campaign_id)
    if row is not None:
        pinned, _ = get_geometry_plan(db, campaign_id)
        if config is not None and config != pinned.config:
            raise ValueError("Cannot silently reconfigure G1")
        return row
    plan = build_geometry_plan(sampler.plan, get_hydrology_plan(db, campaign_id), hr.signature, config)
    row = GenesisHydroGeometryPlan(campaign_id=campaign_id, geometry_version=1,
        signature=plan.signature, config=plan.config.model_dump(), plan=plan.to_dict())
    db.add(row)
    db.flush()
    return row


def get_geometry_plan(db, campaign_id):
    sampler = get_terrain_sampler(db, campaign_id)
    hr, _, _ = hr_header(db, campaign_id)
    h1, _ = h1_header(db, campaign_id)
    row = db.get(GenesisHydroGeometryPlan, campaign_id)
    if row is None:
        raise ValueError("Initialize G1 explicitly; existing saves are not converted")
    config = G1Config.model_validate(row.config)
    expected = signature_for(sampler.plan, h1.payload_checksum, hr.signature, config)
    descriptor = {"kind": "local_hydro_geometry_g1", "geometry_version": 1, "signature": expected,
        "terrain_signature": sampler.plan.signature, "terrain_checksum": checksum(sampler.plan.to_dict()),
        "hydrology_signature": h1.signature, "hydrology_checksum": h1.payload_checksum,
        "hr_signature": hr.signature, "config": config.model_dump(),
        "coast_policy_version": 1, "height_authority": "T1", "water_occupation": "not_modeled"}
    if type(row.geometry_version) is not int or row.geometry_version != 1 or row.signature != expected or row.plan != descriptor:
        raise ValueError("G1 source/version/configuration changed")
    with _lock:
        plan = _cache.get(expected)
        if plan is not None:
            _cache.move_to_end(expected)
            return plan, sampler
    plan = build_geometry_plan(sampler.plan, get_hydrology_plan(db, campaign_id), hr.signature, config)
    if plan.to_dict() != descriptor:
        raise ValueError("G1 source payload mismatch")
    with _lock:
        _cache[expected] = plan
        while len(_cache) > 2:
            _cache.popitem(last=False)
    return plan, sampler


def _ranges(box, level):
    a, b, c, d = (Fraction(*v) for v in box["bounds"])
    n = 2**level
    def lower(v):
        q = v*n
        return max(0, q.numerator//q.denominator-(q.denominator == 1))
    def upper(v):
        q = v*n
        return min(n-1, q.numerator//q.denominator)
    return lower(a), upper(b), lower(c), upper(d)


def _overlaps(row, boxes):
    for box in boxes:
        if row.face == box["face"]:
            x0, x1, y0, y1 = _ranges(box, row.level)
            if x0 <= row.x <= x1 and y0 <= row.y <= y1:
                return True
    return False


def _terrain_events(db, campaign_id, boxes):
    # Dirty identity-map state matters with autoflush=False. Do not flush callers.
    for row in db.dirty | db.new:
        if isinstance(row, GenesisTerrainTile) and row.campaign_id == campaign_id and row.changes and _overlaps(row, boxes):
            raise ValueError("G1 evidence intersects T1 events; event-aware revision required")
    conditions = []
    for box in boxes:
        for level in range(47):
            x0, x1, y0, y1 = _ranges(box, level)
            conditions.append(and_(GenesisTerrainTile.face == box["face"], GenesisTerrainTile.level == level,
                GenesisTerrainTile.x.between(x0, x1), GenesisTerrainTile.y.between(y0, y1)))
    headers = db.query(GenesisTerrainTile.face, GenesisTerrainTile.level, GenesisTerrainTile.x,
        GenesisTerrainTile.y, GenesisTerrainTile.changes).filter(GenesisTerrainTile.campaign_id == campaign_id,
            GenesisTerrainTile.changes != {}, or_(*conditions))
    for face, level, x, y, changes in headers.yield_per(32):
        tracked = db.identity_map.get(identity_key(GenesisTerrainTile, (campaign_id, face, level, x, y)))
        if (tracked.changes if tracked is not None else changes):
            raise ValueError("G1 evidence intersects T1 events; event-aware revision required")


def _provenance(db, campaign_id, plan, request):
    if request.origin == "explicit_boundary_contract":
        return
    node = request.provenance.get("hr1_node")
    if type(node) is not int:
        raise ValueError("G1 HR1 provenance is incomplete")
    row = db.get(GenesisHydrologyRegion, (campaign_id, node))
    if row is None:
        raise ValueError("Pinned G1 HR1 evidence disappeared")
    row = materialize_hydrology_region(db, campaign_id, node)
    if (row.changes or row.signature != plan.hr_signature or
            checksum(row.baseline) != request.provenance.get("hr1_checksum")):
        raise ValueError("G1 HR1 evidence/events changed; refusing regeneration")


def materialize_geometry(db, campaign_id, request):
    plan, sampler = get_geometry_plan(db, campaign_id)
    _provenance(db, campaign_id, plan, request)
    rid = request_id(plan, request)
    row = db.get(GenesisHydroGeometryEvidence, (campaign_id, rid))
    if row is not None:
        if checksum(row.baseline) != row.baseline_checksum:
            raise ValueError("G1 checksum mismatch; refusing regeneration")
        validate_geometry(plan, request, row.baseline)
        _terrain_events(db, campaign_id, row.baseline["terrain_coverage"])
        return row
    tile = TerrainTile(*request.tile)
    _terrain_events(db, campaign_id, coverage_boxes([tile.point(x, y, 1) for x in (0, 1) for y in (0, 1)]))
    data = build_geometry(plan, sampler, request)
    _terrain_events(db, campaign_id, data["terrain_coverage"])
    row = GenesisHydroGeometryEvidence(campaign_id=campaign_id, request_id=rid,
        baseline=data, baseline_checksum=checksum(data), changes={})
    db.add(row)
    db.flush()
    return row


def prepare_regional_geometry(db, campaign_id, node, **options):
    plan, sampler = get_geometry_plan(db, campaign_id)
    hr = materialize_hydrology_region(db, campaign_id, node)
    if hr.changes:
        raise ValueError("G1 needs unchanged HR1 baseline evidence")
    settings = {"candidate_ports": False, "grid_intervals": 8, "target_spacing_m": 100,
                "sample_budget": 8192, "expansion_budget": 4096}
    if set(options)-settings.keys():
        raise ValueError("Unsupported G1 regional preparation options")
    settings.update(options)
    if type(settings["candidate_ports"]) is not bool:
        raise ValueError("G1 candidate_ports must be an explicit boolean")
    preparation_key = checksum(["g1-regional-preparation", plan.signature, hr.baseline_checksum, settings])
    existing = db.query(GenesisHydroGeometryEvidence).filter_by(campaign_id=campaign_id, preparation_key=preparation_key).first()
    if existing is not None:
        # No terrain sampling or port selection when returning to a saved area.
        return materialize_geometry(db, campaign_id, GeometryRequest.model_validate(existing.baseline["request"]))
    request = regional_request(plan, sampler, hr.baseline, **settings)
    row = materialize_geometry(db, campaign_id, request)
    row.preparation_key = preparation_key
    db.flush()
    return row


def get_geometry(db, campaign_id, rid, *, baseline_only=False):
    if type(baseline_only) is not bool:
        raise ValueError("G1 baseline policy must be an explicit boolean")
    plan, _ = get_geometry_plan(db, campaign_id)
    row = db.get(GenesisHydroGeometryEvidence, (campaign_id, rid))
    if row is None:
        raise ValueError("Prepare G1 explicitly; missing evidence is not a physical obstruction")
    if checksum(row.baseline) != row.baseline_checksum:
        raise ValueError("G1 checksum mismatch; refusing regeneration")
    request = GeometryRequest.model_validate(row.baseline["request"])
    validate_geometry(plan, request, row.baseline)
    if not baseline_only:
        if row.changes:
            raise ValueError("G1 events require a versioned geometry overlay")
        _provenance(db, campaign_id, plan, request)
        _terrain_events(db, campaign_id, row.baseline["terrain_coverage"])
    return {"baseline": row.baseline, "baseline_checksum": row.baseline_checksum,
            "changes": row.changes, "baseline_only": baseline_only, "changes_applied": False}
