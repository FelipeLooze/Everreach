"""Explicit H1 persistence; caller owns commit/rollback; no ticks or workers."""
from collections import OrderedDict
import hashlib
import json
from threading import RLock

from sqlalchemy.orm import Session

from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_hydrology import GenesisHydrologyPlan, GenesisHydrologySector
from ..formation_plan import load_plan
from ..formation_v4 import FormationConfigV4
from ..sphere_config import parse_config
from ..sphere_topology import CellKey
from .config import HydrologyConfig
from .plan import HydrologyPlan, build_hydrology_plan, load_hydrology_plan, signature
from .sectors import sector_snapshot

_CACHE_LIMIT = 2
_cache: OrderedDict[tuple[str, str], HydrologyPlan] = OrderedDict()
_lock = RLock()


def payload_checksum(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clear_plan_cache() -> None:
    with _lock:
        _cache.clear()


def plan_cache_size() -> int:
    with _lock:
        return len(_cache)


def _remember(key, plan):
    with _lock:
        _cache[key] = plan
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_LIMIT:
            _cache.popitem(last=False)


def _source(db: Session, campaign_id: str):
    world = db.get(GenesisWorld, campaign_id)
    if world is None:
        raise ValueError("Initialize an explicit V4 world before hydrology")
    config = parse_config(world.config)
    if not isinstance(config, FormationConfigV4):
        raise ValueError("H1 is opt-in for V4; legacy worlds are preserved without conversion")
    if world.plan.get("config") != world.config or world.plan.get("seed") != world.world_seed:
        raise ValueError("Source world configuration is inconsistent")
    return world, config


def _header(db: Session, campaign_id: str):
    world, source_config = _source(db, campaign_id)
    row = db.get(GenesisHydrologyPlan, campaign_id)
    if row is None:
        raise ValueError("Initialize H1 explicitly before querying hydrology")
    config = HydrologyConfig.model_validate(row.config)
    if (type(row.hydrology_version) is not int or row.hydrology_version != 1 or
            row.source_signature != world.plan.get("signature") or row.source_checksum != payload_checksum(world.plan)
            or row.signature != signature(row.source_signature, config)):
        raise ValueError("Hydrology source, version or pinned configuration changed")
    return row, source_config


def initialize_hydrology(db: Session, campaign_id: str, config: HydrologyConfig | None = None) -> GenesisHydrologyPlan:
    world, source_config = _source(db, campaign_id)
    existing = db.get(GenesisHydrologyPlan, campaign_id)
    if existing is not None:
        row, _ = _header(db, campaign_id)
        if config is not None and config != HydrologyConfig.model_validate(row.config):
            raise ValueError("Cannot silently reconfigure an existing hydrology plan")
        return row
    config = config or HydrologyConfig()
    source = load_plan(world.plan, world.world_seed, source_config)
    plan = build_hydrology_plan(source, config)
    payload = plan.to_dict()
    checksum = payload_checksum(payload)
    row = GenesisHydrologyPlan(campaign_id=campaign_id, hydrology_version=1,
        source_signature=source.signature, source_checksum=payload_checksum(world.plan),
        signature=plan.signature, config=config.model_dump(), payload_checksum=checksum, plan=payload)
    db.add(row)
    db.flush()
    _remember((row.signature, checksum), plan)
    return row


def get_hydrology_plan(db: Session, campaign_id: str) -> HydrologyPlan:
    row, source_config = _header(db, campaign_id)
    key = row.signature, row.payload_checksum
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached
    data = row.plan
    if payload_checksum(data) != row.payload_checksum:
        raise ValueError("Hydrology payload checksum mismatch; refusing regeneration")
    plan = load_hydrology_plan(data, row.source_signature, source_config.radius_m, source_config.sea_level_m)
    if plan.signature != row.signature or plan.config != HydrologyConfig.model_validate(row.config):
        raise ValueError("Hydrology payload differs from its pinned header")
    _remember(key, plan)
    return plan


def materialize_hydrology_sector(db: Session, campaign_id: str, key: CellKey) -> GenesisHydrologySector:
    row, source_config = _header(db, campaign_id)
    if not isinstance(key, CellKey) or key.level != source_config.sector_level:
        raise ValueError("Hydrology snapshots require the world's pinned sector level")
    existing = db.get(GenesisHydrologySector, (campaign_id, key.face, key.x, key.y))
    if existing is not None:
        if (existing.baseline.get("hydrology_signature") != row.signature or
                existing.baseline.get("hydrology_version") != 1 or
                existing.baseline.get("source_signature") != row.source_signature or
                existing.baseline.get("sector") != [key.face, key.level, key.x, key.y]):
            raise ValueError("Sector belongs to a different hydrology plan")
        return existing
    plan = get_hydrology_plan(db, campaign_id)
    sector = GenesisHydrologySector(campaign_id=campaign_id, face=key.face, x=key.x, y=key.y,
                                   baseline=sector_snapshot(plan, key), changes={})
    db.add(sector)
    db.flush()
    return sector
