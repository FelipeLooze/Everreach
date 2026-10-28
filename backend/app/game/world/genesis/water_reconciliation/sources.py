"""Historical W1 reader: live HR1 events do NOT erase sealed past balances."""
from collections import OrderedDict
from threading import RLock
from app.db.models.world_water import GenesisWaterPlan
from ..water.config import parse_water_config,check_climate_contract
from ..climate.dispatch import parse_climate_config
from ..water.plan import load_water_plan, checksum, signature as w1_signature
from ..hydrology.service import _header as h1_header, get_hydrology_plan
from ..hydrology.regional_service import _header as hr_header
from ..climate.service import _header as climate_header, get_climate_plan

_cache, _lock = OrderedDict(), RLock()


def clear_baseline_cache():
    with _lock:
        _cache.clear()


def water_baseline(db, campaign_id):
    row = db.get(GenesisWaterPlan, campaign_id)
    if row is None:
        raise ValueError("W2 requires explicitly prepared W1")
    h1, _ = h1_header(db, campaign_id)
    hr, _, _ = hr_header(db, campaign_id)
    climate, _ = climate_header(db, campaign_id)
    config = parse_water_config(row.config)
    manifest = tuple(tuple(x) for x in row.manifest)
    if (type(row.water_version) is not int or row.water_version != 1 or config.source_climate_version not in (2,3) or
            row.hydrology_signature != h1.signature or row.hydrology_checksum != h1.payload_checksum or
            row.hr_signature != hr.signature or row.climate_signature != climate.signature or
            row.climate_checksum != climate.payload_checksum or
            row.signature != w1_signature(h1.signature, climate.signature, hr.signature, config, manifest)):
        raise ValueError("W2 immutable W1/C2 source headers changed")
    check_climate_contract(config,parse_climate_config(climate.config))
    key = row.signature, row.payload_checksum
    with _lock:
        value = _cache.get(key)
        if value is not None:
            _cache.move_to_end(key)
            return row, value
    data = row.plan
    if checksum(data) != row.payload_checksum:
        raise ValueError("W1 historical checksum mismatch; refusing regeneration")
    value = load_water_plan(data, get_hydrology_plan(db, campaign_id), get_climate_plan(db, campaign_id), hr.signature)
    if value.signature != row.signature or value.manifest != manifest:
        raise ValueError("W1 historical payload/header mismatch")
    with _lock:
        _cache[key] = value
        while len(_cache) > 2:
            _cache.popitem(last=False)
    return row, value
