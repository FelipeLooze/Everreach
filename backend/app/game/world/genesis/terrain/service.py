"""Opt-in T1 authority. No commits, automatic migration, or water rebalancing."""
from collections import OrderedDict
from threading import RLock
from sqlalchemy import and_, or_
from app.db.models.world_terrain import GenesisTerrainPlan, GenesisTerrainTile
from app.db.models.world_spatial import GenesisSphereSector
from ..formation_plan import load_plan
from ..hydrology.service import _source
from ..sphere_topology import BASES, SurfacePoint
from .address import TerrainTile, chart
from .config import TerrainConfig
from .field import TerrainSampler, build_terrain_plan, checksum
from .patch import prepare_patch, saved_sample, validate_patch

_cache, _lock = OrderedDict(), RLock()


def clear_terrain_cache():
    with _lock:
        _cache.clear()


def terrain_cache_size():
    with _lock:
        return len(_cache)


def initialize_terrain(db, campaign_id, config=None):
    world, source_config = _source(db, campaign_id)
    row = db.get(GenesisTerrainPlan, campaign_id)
    if row is not None:
        sampler = get_terrain_sampler(db, campaign_id)
        if config is not None and config != sampler.plan.config:
            raise ValueError("Cannot silently reconfigure T1")
        return row
    if db.query(GenesisSphereSector.face).filter(GenesisSphereSector.campaign_id == campaign_id).first() is not None:
        raise ValueError("Materialized V4 sectors require an explicit terrain-authority migration before T1 activation")
    plan = build_terrain_plan(load_plan(world.plan, world.world_seed, source_config), config)
    row = GenesisTerrainPlan(campaign_id=campaign_id, terrain_version=1, signature=plan.signature,
        source_checksum=plan.source_checksum, config=plan.config.model_dump(), plan=plan.to_dict())
    db.add(row)
    db.flush()
    return row


def get_terrain_sampler(db, campaign_id):
    world, config = _source(db, campaign_id)
    row = db.get(GenesisTerrainPlan, campaign_id)
    if row is None:
        raise ValueError("Initialize T1 explicitly; legacy authority is preserved")
    source_hash = checksum(world.plan)
    if type(row.terrain_version) is not int or row.terrain_version != 1 or row.source_checksum != source_hash:
        raise ValueError("T1 source or version changed; refusing regeneration")
    key = row.signature, checksum(row.plan), source_hash, checksum(row.config)
    with _lock:
        sampler = _cache.get(key)
        if sampler is not None:
            _cache.move_to_end(key)
            return sampler
    # This constructs a small descriptor, never rebuilds V4 or local terrain.
    plan = build_terrain_plan(load_plan(world.plan, world.world_seed, config), TerrainConfig.model_validate(row.config))
    if row.plan != plan.to_dict() or row.signature != plan.signature:
        raise ValueError("T1 pinned descriptor mismatch")
    sampler = TerrainSampler(plan)
    with _lock:
        _cache[key] = sampler
        while len(_cache) > 2:
            _cache.popitem(last=False)
    return sampler


def _validate_saved(sampler, tile, row):
    if checksum(row.baseline) != row.baseline_checksum:
        raise ValueError("T1 saved checksum mismatch; refusing regeneration")
    validate_patch(sampler.plan, tile, row.baseline)


def materialize_terrain_tile(db, campaign_id, tile):
    if not isinstance(tile, TerrainTile):
        raise ValueError("T1 needs an explicit TerrainTile")
    sampler = get_terrain_sampler(db, campaign_id)
    row = db.get(GenesisTerrainTile, (campaign_id, tile.face, tile.level, tile.x, tile.y))
    if row is not None:
        _validate_saved(sampler, tile, row)
        return row
    data = prepare_patch(sampler, tile)
    row = GenesisTerrainTile(campaign_id=campaign_id, **vars(tile), baseline=data,
        baseline_checksum=checksum(data), changes={})
    db.add(row)
    db.flush()
    return row


def query_altitude(db, campaign_id, point, *, baseline_only=False):
    """Single opt-in authority, in mm; persisted sample points always win.

    Modification physics is deferred. Uninterpreted events MUST NOT silently
    return an allegedly current generated surface. baseline_only is explicit.
    """
    if not isinstance(point, SurfacePoint) or type(baseline_only) is not bool:
        raise ValueError("T1 requires an exact point and explicit boolean baseline policy")
    sampler = get_terrain_sampler(db, campaign_id)
    # Closed coverage on every incident face/edge/corner; includes BOTH tiles
    # at internal grid boundaries so events cannot leak through seam ownership.
    predicates = []
    maximum = max(map(abs, point.xyz))
    for face, (normal, _, _) in enumerate(BASES):
        if sum(a*b for a, b in zip(normal, point.xyz)) != maximum:
            continue
        _, u, v, d = chart(point, face)
        for level in range(47):
            n = 2**level
            xs = {min(n-1, u*n//d)} | ({u*n//d-1} if u*n%d == 0 and u else set())
            ys = {min(n-1, v*n//d)} | ({v*n//d-1} if v*n%d == 0 and v else set())
            predicates.append(and_(GenesisTerrainTile.face == face, GenesisTerrainTile.level == level,
                GenesisTerrainTile.x.in_(xs), GenesisTerrainTile.y.in_(ys)))
    rows = db.query(GenesisTerrainTile).filter(GenesisTerrainTile.campaign_id == campaign_id, or_(*predicates)).all()
    result = None
    for row in rows:
        tile = TerrainTile(row.face, row.level, row.x, row.y)
        _validate_saved(sampler, tile, row)
        if row.changes and not baseline_only:
            raise ValueError("T1 terrain events require an event-aware overlay; use explicit baseline_only for diagnostics")
        sample = saved_sample(row.baseline, tile, point)
        if sample is not None:
            if result is not None and result != sample:
                raise ValueError("Persisted T1 LODs disagree")
            result = sample
    if result is None:
        result = sampler.sample(point)
    return {**result, "terrain_version": 1, "signature": sampler.plan.signature, "point": list(point.xyz),
            "authority": "full_spectrum_point_field", "base_level": sampler.plan.base_level,
            "minimum_wavelength_m": sampler.plan.to_dict()["minimum_wavelength_m"],
            "baseline_only": baseline_only, "modifications_applied": False}


def query_hydrology_constraints(db, campaign_id, node):
    """Inspect already saved HR1 only; exploration never extends the W1 manifest."""
    from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
    from app.db.models.world_water import GenesisWaterPlan
    from ..hydrology.service import get_hydrology_plan
    from ..hydrology.regional_service import materialize_hydrology_region
    from ..water.service import get_water_plan
    from .hydrology import audit_regional_constraints
    if type(node) is not int:
        raise ValueError("Expected an integer HR1 address")
    row = db.get(GenesisHydrologyRegion, (campaign_id, node))
    if row is None:
        raise ValueError("Prepare HR1 explicitly before T1 inspection")
    # Existing-row path validates signatures and checksums without generating it.
    row = materialize_hydrology_region(db, campaign_id, node)
    if row.changes:
        raise ValueError("Modified HR1 requires an event-aware terrain/hydrology overlay")
    water = get_water_plan(db, campaign_id) if db.get(GenesisWaterPlan, campaign_id) is not None else None
    return audit_regional_constraints(get_terrain_sampler(db, campaign_id), get_hydrology_plan(db, campaign_id), row.baseline, water)
