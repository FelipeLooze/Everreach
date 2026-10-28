"""Caller-owned persistence, explicit C1 opt-in and an immutable two-plan cache."""
from collections import OrderedDict
from threading import RLock

from app.db.models.world_climate import GenesisClimatePlan, GenesisClimateSector
from ..formation_plan import load_plan
from ..hydrology.service import _header as h1_header, _source, get_hydrology_plan, payload_checksum
from ..sphere_topology import CellKey, cell_center
from .config import ClimateConfig
from .dispatch import parse_climate_config
from .plan import build_climate_plan, load_climate_plan, signature
from .query import sample_climate, sample_regional_climate

_cache = OrderedDict()
_lock = RLock()


def clear_climate_cache():
    with _lock:
        _cache.clear()


def climate_cache_size():
    with _lock:
        return len(_cache)


def _remember(key, plan):
    with _lock:
        _cache[key] = plan
        _cache.move_to_end(key)
        while len(_cache) > 2:
            _cache.popitem(last=False)


def _header(db, campaign_id):
    h1, source_config = h1_header(db, campaign_id)
    row = db.get(GenesisClimatePlan, campaign_id)
    if row is None:
        raise ValueError("Initialize C1 explicitly; old saves are not converted")
    config = parse_climate_config(row.config)
    if (type(row.climate_version) is not int or row.climate_version != config.climate_version
            or row.source_signature != h1.source_signature or row.source_checksum != h1.source_checksum
            or row.hydrology_signature != h1.signature or row.hydrology_checksum != h1.payload_checksum
            or row.signature != signature(row.source_signature, row.hydrology_signature, config)):
        raise ValueError("C1 version, source or pinned configuration changed")
    return row, source_config


def initialize_climate(db, campaign_id, config=None):
    h1_row, source_config = h1_header(db, campaign_id)
    existing = db.get(GenesisClimatePlan, campaign_id)
    if existing is not None:
        row, _ = _header(db, campaign_id)
        if config is not None and config != parse_climate_config(row.config):
            raise ValueError("Cannot silently reconfigure C1")
        return row
    config = config or ClimateConfig()
    world, _ = _source(db, campaign_id)
    source = load_plan(world.plan, world.world_seed, source_config)
    plan = build_climate_plan(source, get_hydrology_plan(db, campaign_id), config)
    payload = plan.to_dict()
    row = GenesisClimatePlan(campaign_id=campaign_id, climate_version=config.climate_version,
        source_signature=plan.source_signature, source_checksum=h1_row.source_checksum,
        hydrology_signature=plan.hydrology_signature, hydrology_checksum=h1_row.payload_checksum,
        signature=plan.signature, config=config.model_dump(), payload_checksum=payload_checksum(payload), plan=payload)
    db.add(row)
    db.flush()
    _remember((row.signature, row.payload_checksum), plan)
    return row


def get_climate_plan(db, campaign_id):
    row, source_config = _header(db, campaign_id)
    key = row.signature, row.payload_checksum
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    data = row.plan
    if payload_checksum(data) != row.payload_checksum:
        raise ValueError("C1 payload checksum mismatch; refusing regeneration")
    plan = load_climate_plan(data, row.source_signature, row.hydrology_signature,
                             source_config.radius_m, source_config.sea_level_m)
    if plan.signature != row.signature or plan.config != parse_climate_config(row.config):
        raise ValueError("C1 payload differs from pinned header")
    _remember(key, plan)
    return plan


def query_climate(db, campaign_id, point, *, regional=True):
    plan = get_climate_plan(db, campaign_id)
    if not regional:
        return sample_climate(plan, point)
    world, config = _source(db, campaign_id)
    return sample_regional_climate(load_plan(world.plan, world.world_seed, config), plan, point)


def materialize_climate_sector(db, campaign_id, key):
    row, source_config = _header(db, campaign_id)
    if not isinstance(key, CellKey) or key.level != source_config.sector_level:
        raise ValueError("C1 snapshot requires the world's pinned sector level")
    existing = db.get(GenesisClimateSector, (campaign_id, key.face, key.x, key.y))
    if existing is not None:
        data = existing.baseline
        if (data.get("signature") != row.signature or data.get("climate_version") != row.climate_version
                or data.get("sector") != [key.face, key.level, key.x, key.y]
                or existing.baseline_checksum != payload_checksum(data)):
            raise ValueError("C1 snapshot mismatch; refusing regeneration")
        return existing
    snapshot = query_climate(db, campaign_id, cell_center(key))
    snapshot["sector"] = [key.face, key.level, key.x, key.y]
    snapshot["coverage"] = "sector_center_sample_not_a_uniform_sector_climate"
    sector = GenesisClimateSector(campaign_id=campaign_id, face=key.face, x=key.x, y=key.y,
        baseline=snapshot, baseline_checksum=payload_checksum(snapshot), changes={})
    db.add(sector)
    db.flush()
    return sector
