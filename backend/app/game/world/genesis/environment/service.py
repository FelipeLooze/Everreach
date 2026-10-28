"""Explicit E1 persistence, never a map/gameplay spawn or a source of vegetation."""
from collections import OrderedDict
from copy import deepcopy
import json
from threading import RLock
from sqlalchemy import update
from app.db.models.world_environment import GenesisEnvironmentPlan,GenesisEnvironmentPoint
from ..geology.regional.service import (context as regional_context,materialize_regional_formation,
    _validate_formation as validate_regional_baseline,_parent_current)
from app.db.models.world_geology_regional import GenesisRegionalFormation
from ..climate.service import get_climate_plan
from ..hydrology.service import get_hydrology_plan
from ..terrain.service import query_altitude
from ..terrain.field import checksum
from .adapter import EnvironmentSampler
from .config import EnvironmentConfig,parse_environment_config,source_climate_version

_cache=OrderedDict()
_lock=RLock()


def clear_environment_cache():
    with _lock:_cache.clear()


def initialize_environment(db,campaign_id,config=None):
    row=db.get(GenesisEnvironmentPlan,campaign_id)
    if row is not None:
        sampler=get_environment_sampler(db,campaign_id)
        if config is not None and config!=sampler.config:
            raise ValueError("Cannot silently reconfigure E1")
        return row
    _,regional,_=regional_context(db,campaign_id)
    sampler=EnvironmentSampler(regional,get_hydrology_plan(db,campaign_id),get_climate_plan(db,campaign_id),config)
    row=GenesisEnvironmentPlan(campaign_id=campaign_id,environment_version=1,signature=sampler.signature,
        descriptor=sampler.descriptor,descriptor_checksum=checksum(sampler.descriptor),write_epoch=0)
    db.add(row);db.flush()
    with _lock:
        _cache[(sampler.signature,row.descriptor_checksum)]=sampler
        while len(_cache)>2:_cache.popitem(last=False)
    return row


def get_environment_sampler(db,campaign_id):
    row=db.get(GenesisEnvironmentPlan,campaign_id)
    if row is None:
        raise ValueError("Initialize E1 explicitly; no environmental auto-generation")
    if type(row.environment_version) is not int or row.environment_version!=1 or checksum(row.descriptor)!=row.descriptor_checksum:
        raise ValueError("E1 pinned version/descriptor mismatch")
    _,regional,_=regional_context(db,campaign_id)
    climate,h1=get_climate_plan(db,campaign_id),get_hydrology_plan(db,campaign_id)
    d=row.descriptor
    pinned_config=parse_environment_config(d['config'])
    if (climate.config.climate_version!=source_climate_version(pinned_config) or regional.signature!=d["jr1_signature"] or regional.descriptor!=d["jr1_descriptor"] or
            climate.signature!=d["climate_signature"] or h1.signature!=d["hydrology_signature"] or
            checksum(climate.to_dict())!=d["climate_checksum"] or checksum(h1.to_dict())!=d["hydrology_checksum"]):
        raise ValueError("E1 physical source changed; refusing regeneration")
    key=row.signature,row.descriptor_checksum
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    sampler=EnvironmentSampler(regional,h1,climate,pinned_config)
    if sampler.descriptor!=d or sampler.signature!=row.signature:
        raise ValueError("E1 pinned environmental configuration mismatch")
    with _lock:
        _cache[key]=sampler
        while len(_cache)>2:_cache.popitem(last=False)
    return sampler


def _identifier(sampler,point):
    return "env:"+checksum([sampler.signature,list(point.xyz)])[:32]


def _validate(row,sampler,point):
    if (row.probe_id!=_identifier(sampler,point) or row.point!=list(point.xyz) or
            checksum(row.baseline)!=row.baseline_checksum or row.baseline["authority_signature"]!=sampler.signature or
            row.baseline["probe_id"]!=row.probe_id or row.baseline["point"]!=row.point or
            row.baseline["hierarchy"]["regional_formation_id"]!=row.formation_id):
        raise ValueError("Established E1 snapshot mismatch; no regeneration")


def seal_physical_classification(data):
    data=deepcopy(data)
    confirmed=[]
    for record in data["results"]:
        if record["state"]=="elegivel" and not record["vegetation_establishment_required"] and not record["confirmation_missing"]:
            record["state"]="confirmado"
            record["confirmation_scope"]="persisted_physical_point_classification_not_species_or_unmodeled_feature"
            confirmed.append(record["environment_id"])
    data["confirmed_physical_ids"]=confirmed
    data["primary_confirmed"]=data["primary_potential"] if data["primary_potential"] in confirmed else None
    data["persisted_classification"]=True
    return data


def _geological_context(db,campaign_id,sampler,point,*,prepare=False):
    """Physical JR1 projection only: ore balances do not determine environments."""
    identifier=sampler.regional.address(point)[3]
    formation=db.get(GenesisRegionalFormation,(campaign_id,identifier))
    if formation is None and prepare:
        formation=materialize_regional_formation(db,campaign_id,point,experimental_sources=False)
    if formation is None:
        raise ValueError("Missing persisted JR1 source formation")
    if formation not in db.dirty:db.refresh(formation)
    validate_regional_baseline(formation,sampler.regional)
    _parent_current(db,campaign_id,formation,sampler.regional)
    if formation.changes:
        raise ValueError("Regional geological changes require an explicit overlay")
    from ..sphere_topology import SurfacePoint
    query_altitude(db,campaign_id,SurfacePoint(*formation.baseline["anchor_point"]))
    return formation


def materialize_environment_point(db,campaign_id,point,*,_sampler=None):
    sampler=_sampler if _sampler is not None else get_environment_sampler(db,campaign_id)
    identifier=_identifier(sampler,point)
    if db.get_bind().dialect.name!="sqlite":
        raise ValueError("E1 transactional writer fence is validated only for SQLite")
    db.flush()
    db.execute(update(GenesisEnvironmentPlan).where(GenesisEnvironmentPlan.campaign_id==campaign_id).
        values(write_epoch=GenesisEnvironmentPlan.write_epoch+1),execution_options={"synchronize_session":False})
    with db.begin_nested():
        row=db.get(GenesisEnvironmentPoint,(campaign_id,identifier),populate_existing=True)
        if row is not None:
            _validate(row,sampler,point)
            return row
        formation=_geological_context(db,campaign_id,sampler,point,prepare=True)
        query_altitude(db,campaign_id,point)
        data=sampler.sample(point)
        if data["physical_inputs"]["JR1_checksum"]!=formation.baseline_checksum:
            raise ValueError("E1 substrate differs from the persisted JR1 formation")
        data=seal_physical_classification(data)
        if len(json.dumps(data,separators=(",",":")).encode())>1048576:
            raise ValueError("E1 local snapshot budget exceeded")
        row=GenesisEnvironmentPoint(campaign_id=campaign_id,probe_id=identifier,formation_id=formation.formation_id,
            point=list(point.xyz),baseline=data,baseline_checksum=checksum(data),changes={})
        db.add(row);db.flush()
        return row


def query_environment(db,campaign_id,point,*,baseline_only=False,_sampler=None):
    if type(baseline_only) is not bool:
        raise ValueError("Explicit E1 event policy required")
    sampler=_sampler if _sampler is not None else get_environment_sampler(db,campaign_id)
    row=db.get(GenesisEnvironmentPoint,(campaign_id,_identifier(sampler,point)))
    if row is None:
        raise ValueError("E1 point not materialized; query does not create an environment")
    if row not in db.dirty:db.refresh(row)
    _validate(row,sampler,point)
    if row.changes and not baseline_only:
        raise ValueError("Environmental world changes require an explicit overlay")
    if not baseline_only:
        _geological_context(db,campaign_id,sampler,point)
        query_altitude(db,campaign_id,point)
    return {"baseline":deepcopy(row.baseline),"changes":deepcopy(row.changes),"baseline_only":baseline_only,
        "flora_generated":False,"fauna_generated":False,"spawn_authorized":False}
