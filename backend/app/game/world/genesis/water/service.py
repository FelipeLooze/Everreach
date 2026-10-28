"""Explicit W1 preparation with fixed HR1 evidence. Caller owns transactions."""
from collections import OrderedDict
from threading import RLock
from sqlalchemy.orm.util import identity_key

from app.db.models.world_water import GenesisWaterPlan, GenesisWaterSector
from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
from ..formation_plan import load_plan, cell_index
from ..sphere_topology import CellKey
from ..hydrology.service import _header as h1_header, _source, get_hydrology_plan
from ..hydrology.regional_service import _header as hr_header, materialize_hydrology_region
from ..climate.service import _header as climate_header, get_climate_plan
from .config import WaterConfig,parse_water_config,check_climate_contract
from ..climate.dispatch import parse_climate_config
from .plan import MAX_EVIDENCE_REGIONS, build_water_plan, load_water_plan, compile_evidence, checksum, signature
from .query import regional_sector_record

_cache, _lock = OrderedDict(), RLock()


def clear_water_cache():
    with _lock:
        _cache.clear()


def water_cache_size():
    with _lock:
        return len(_cache)


def _remember(key, plan):
    with _lock:
        _cache[key] = plan
        _cache.move_to_end(key)
        while len(_cache) > 2:
            _cache.popitem(last=False)


def _evidence_headers(db, campaign_id, manifest, expected_hr):
    nodes = [node for node, _ in manifest]
    if len(nodes) > MAX_EVIDENCE_REGIONS or len(set(nodes)) != len(nodes):
        raise ValueError("Invalid W1 evidence budget")
    if not nodes:
        return
    headers = db.query(GenesisHydrologyRegion.node, GenesisHydrologyRegion.signature,
        GenesisHydrologyRegion.baseline_checksum, GenesisHydrologyRegion.changes).filter(
            GenesisHydrologyRegion.campaign_id == campaign_id, GenesisHydrologyRegion.node.in_(nodes)).all()
    if len(headers) != len(nodes):
        raise ValueError("W1 regional evidence disappeared; refusing regeneration")
    checksums = dict(manifest)
    for node, regional_signature, baseline_checksum, changes in headers:
        # Sessions in this project may disable autoflush. Pending world events
        # must be observed without flushing unrelated caller-owned work.
        tracked = db.identity_map.get(identity_key(GenesisHydrologyRegion, (campaign_id, node)))
        if tracked is not None:
            regional_signature, baseline_checksum, changes = tracked.signature, tracked.baseline_checksum, tracked.changes
        if regional_signature != expected_hr or baseline_checksum != checksums[node] or changes:
            raise ValueError("W1 regional evidence changed; event-aware water overlay is required")


def _header(db, campaign_id):
    h1, source_config = h1_header(db, campaign_id)
    climate, _ = climate_header(db, campaign_id)
    hr, hr_config, _ = hr_header(db, campaign_id)
    row = db.get(GenesisWaterPlan, campaign_id)
    if row is None:
        raise ValueError("Initialize W1 explicitly; existing saves are not converted")
    config = parse_water_config(row.config)
    manifest = tuple(tuple(pair) for pair in row.manifest)
    if (type(row.water_version) is not int or row.water_version != 1 or row.hydrology_signature != h1.signature
            or row.hydrology_checksum != h1.payload_checksum or row.climate_signature != climate.signature
            or row.climate_checksum != climate.payload_checksum or row.hr_signature != hr.signature
            or config.source_climate_version != climate.climate_version
            or row.signature != signature(h1.signature, climate.signature, hr.signature, config, manifest)):
        raise ValueError("W1 version/source/configuration changed")
    check_climate_contract(config,parse_climate_config(climate.config))
    _evidence_headers(db, campaign_id, manifest, hr.signature)
    return row, source_config, hr_config


def initialize_water_balance(db, campaign_id, config=None, *, regional_nodes=None):
    requested = None if regional_nodes is None else tuple(regional_nodes)
    if requested is not None and any(type(node) is not int for node in requested):
        raise ValueError("W1 region addresses must be integers")
    existing = db.get(GenesisWaterPlan, campaign_id)
    if existing is not None:
        row, _, _ = _header(db, campaign_id)
        if config is not None and config != parse_water_config(row.config):
            raise ValueError("Cannot silently reconfigure W1")
        if requested is not None and tuple(sorted(set(requested))) != tuple(node for node, _ in row.manifest):
            raise ValueError("Cannot extend W1 evidence from exploration order")
        return row
    config = config or WaterConfig()
    climate_row, source_config = climate_header(db, campaign_id)
    hr, hr_config, _ = hr_header(db, campaign_id)
    h1_row, _ = h1_header(db, campaign_id)
    if config.source_climate_version != climate_row.climate_version:
        raise ValueError("W1 defaults to C2; C1 needs explicit source_climate_version=1 opt-in")
    check_climate_contract(config,parse_climate_config(climate_row.config))
    supplied = requested or ()
    nodes = tuple(sorted(set(supplied)))
    if len(nodes) > MAX_EVIDENCE_REGIONS:
        raise ValueError("W1 preparation accepts at most 32 explicit HR1 nodes")
    regions = []
    for node in nodes:
        saved = materialize_hydrology_region(db, campaign_id, node)
        if saved.changes:
            raise ValueError("Modified HR1 evidence cannot be regenerated or treated as baseline water geometry")
        regions.append(saved.baseline)
    world, _ = _source(db, campaign_id)
    plan = build_water_plan(load_plan(world.plan, world.world_seed, source_config),
        get_hydrology_plan(db, campaign_id), get_climate_plan(db, campaign_id), regions, hr_config, config)
    data = plan.to_dict()
    row = GenesisWaterPlan(campaign_id=campaign_id, water_version=1, signature=plan.signature, config=config.model_dump(),
        hydrology_signature=h1_row.signature, hydrology_checksum=h1_row.payload_checksum,
        climate_signature=climate_row.signature, climate_checksum=climate_row.payload_checksum,
        hr_signature=hr.signature, manifest=list(plan.manifest), payload_checksum=checksum(data), plan=data)
    db.add(row)
    db.flush()
    _remember((row.signature, row.payload_checksum), plan)
    return row


def get_water_plan(db, campaign_id):
    row, _, hr_config = _header(db, campaign_id)
    key = row.signature, row.payload_checksum
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    data = row.plan
    if checksum(data) != row.payload_checksum:
        raise ValueError("W1 checksum mismatch; refusing regeneration")
    plan = load_water_plan(data, get_hydrology_plan(db, campaign_id), get_climate_plan(db, campaign_id), row.hr_signature)
    if plan.signature != row.signature or plan.config != parse_water_config(row.config) or list(plan.manifest) != list(map(tuple, row.manifest)):
        raise ValueError("W1 payload/header mismatch")
    pinned = dict(plan.manifest)
    regions = db.query(GenesisHydrologyRegion).filter(GenesisHydrologyRegion.campaign_id == campaign_id,
        GenesisHydrologyRegion.node.in_(pinned)).all() if pinned else []
    if len(regions) != len(pinned) or any(checksum(r.baseline) != pinned[r.node] or r.changes for r in regions):
        raise ValueError("W1 saved HR1 evidence mismatch; refusing regeneration")
    manifest, support, ports = compile_evidence(plan.hydrology, hr_config, [r.baseline for r in regions])
    if manifest != plan.manifest or support != plan.support or ports != plan.port_ids:
        raise ValueError("W1 transfer proof differs from its fixed HR1 evidence")
    _remember(key, plan)
    return plan


def materialize_water_sector(db, campaign_id, key):
    row, source_config, _ = _header(db, campaign_id)
    if not isinstance(key, CellKey) or key.level != source_config.sector_level:
        raise ValueError("W1 snapshot requires the pinned world sector level")
    existing = db.get(GenesisWaterSector, (campaign_id, key.face, key.x, key.y))
    if existing is not None:
        if (existing.baseline.get("signature") != row.signature or existing.baseline.get("water_version") != 1
                or existing.baseline.get("sector") != [key.face, key.level, key.x, key.y]
                or checksum(existing.baseline) != existing.baseline_checksum):
            raise ValueError("W1 sector mismatch; refusing regeneration")
        return existing
    plan = get_water_plan(db, campaign_id)
    if key.level < plan.hydrology.config.level:
        raise ValueError("W1 query must be inside one canonical H1 region")
    node = cell_index(key.parent(plan.hydrology.config.level))
    region = None
    if node in dict(plan.manifest):
        region = materialize_hydrology_region(db, campaign_id, node).baseline
    data = regional_sector_record(plan, key, region)
    snapshot = GenesisWaterSector(campaign_id=campaign_id, face=key.face, x=key.x, y=key.y,
        baseline=data, baseline_checksum=checksum(data), changes={})
    db.add(snapshot)
    db.flush()
    return snapshot
