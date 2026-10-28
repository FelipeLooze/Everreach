"""JR1 opt-in persistence; finite reserves use the existing J1 deposit table."""
from copy import deepcopy
from sqlalchemy import update
from app.db.models.world_geology import GenesisMineralDeposit,GenesisGeologicalUnit
from app.db.models.world_geology_regional import GenesisRegionalGeology,GenesisRegionalFormation,GenesisRegionalSource
from ..service import get_geology_plan,materialize_geological_unit
from ...terrain.service import get_terrain_sampler,query_altitude
from ...terrain.field import checksum
from ...sphere_topology import SurfacePoint
from .field import RegionalSampler
from .config import RegionalConfig,RegionalPolicy
from .occurrence import opportunities,select_sources


def initialize_regional_geology(db,campaign_id,config=None,policy=None):
    row = db.get(GenesisRegionalGeology,campaign_id)
    if row is not None:
        _,sampler,pinned = context(db,campaign_id)
        if (config is not None and config!=sampler.config) or (policy is not None and policy!=pinned):
            raise ValueError("Cannot silently reconfigure JR1")
        return row
    macro = get_geology_plan(db,campaign_id)
    if db.query(GenesisMineralDeposit.deposit_id).filter_by(campaign_id=campaign_id).first() is not None:
        raise ValueError("Existing macro deposits require explicit allocation migration before JR1 activation")
    sampler = RegionalSampler(macro,get_terrain_sampler(db,campaign_id),config)
    policy = policy or RegionalPolicy()
    row = GenesisRegionalGeology(campaign_id=campaign_id,regional_version=1,signature=sampler.signature,
        descriptor=sampler.descriptor,policy=policy.model_dump(),policy_signature=checksum([sampler.signature,policy.model_dump()]),
        source_checksum=macro.data["checksum"],write_epoch=0)
    db.add(row)
    db.flush()
    return row


def context(db,campaign_id):
    row = db.get(GenesisRegionalGeology,campaign_id)
    if row is None:
        raise ValueError("Initialize JR1 explicitly; no automatic refinement")
    macro = get_geology_plan(db,campaign_id)
    sampler = RegionalSampler(macro,get_terrain_sampler(db,campaign_id),RegionalConfig.model_validate(row.descriptor["config"]))
    if (type(row.regional_version) is not int or row.regional_version!=1 or row.source_checksum!=macro.data["checksum"] or
            row.descriptor!=sampler.descriptor or row.signature!=sampler.signature):
        raise ValueError("JR1 pinned authority mismatch")
    policy = RegionalPolicy.model_validate(row.policy)
    if row.policy_signature!=checksum([sampler.signature,policy.model_dump()]):
        raise ValueError("JR1 pinned occurrence policy mismatch")
    return row,sampler,policy


def _validate_formation(row,sampler):
    b = row.baseline
    if (b.get("kind")!="regional_formation_jr1" or type(b.get("regional_version")) is not int or b["regional_version"]!=1 or
            checksum(b)!=row.baseline_checksum or b["authority_signature"]!=sampler.signature or
            b["formation_id"]!=row.formation_id or b["parent_unit_id"]!=row.parent_unit_id or
            row.formation_id!="jr1:"+checksum([sampler.signature,row.parent_unit_id,b["physical_address"]])[:32]):
        raise ValueError("Established JR1 formation mismatch; refusing regeneration")


def _sources(db,campaign_id,formation):
    if any(isinstance(r,GenesisMineralDeposit) and r.campaign_id==campaign_id for r in db.dirty):
        raise ValueError("Flush finite stock changes before reading JR1 sources")
    rows = db.query(GenesisMineralDeposit).join(GenesisRegionalSource,
        (GenesisRegionalSource.campaign_id==GenesisMineralDeposit.campaign_id)&
        (GenesisRegionalSource.deposit_id==GenesisMineralDeposit.deposit_id)).filter(
        GenesisRegionalSource.campaign_id==campaign_id,GenesisRegionalSource.formation_id==formation.formation_id).order_by(
        GenesisMineralDeposit.deposit_id).populate_existing().all()
    for row in rows:
        if (checksum(row.baseline)!=row.baseline_checksum or row.baseline.get("kind")!="regional_deposit_jr1" or
                row.baseline["formation_id"]!=formation.formation_id or
                not 0<=row.remaining_units<=row.baseline["initial_volume_units"]):
            raise ValueError("Finite JR1 source mismatch; no respawn")
    return rows


def _parent_current(db,campaign_id,formation,sampler,baseline_only=False):
    parent=db.get(GenesisGeologicalUnit,(campaign_id,formation.parent_unit_id))
    if parent is not None and parent not in db.dirty:
        db.refresh(parent)
    expected=next(u for u in sampler.macro.units if u["geological_unit_id"]==formation.parent_unit_id)
    if parent is None or checksum(parent.baseline)!=parent.baseline_checksum or parent.baseline!=expected:
        raise ValueError("JR1 parent J1 authority mismatch")
    if parent.changes and not baseline_only:
        raise ValueError("Parent geological events require reconciliation")


def materialize_regional_formation(db,campaign_id,point,*,experimental_sources=False):
    if type(experimental_sources) is not bool:
        raise ValueError("Explicit experimental boolean required")
    header,sampler,policy = context(db,campaign_id)
    _,_,_,identifier = sampler.address(point)
    if db.get_bind().dialect.name!="sqlite":
        raise ValueError("JR1 writer fence is currently validated only for SQLite")
    db.flush()
    # SQLite writer lock before the savepoint: caller rollback remains authoritative.
    db.execute(update(GenesisRegionalGeology).where(GenesisRegionalGeology.campaign_id==campaign_id).
        values(write_epoch=GenesisRegionalGeology.write_epoch+1),execution_options={"synchronize_session":False})
    with db.begin_nested():
        row = db.get(GenesisRegionalFormation,(campaign_id,identifier),populate_existing=True)
        if row is None:
            data = sampler.formation(point)
            parent = next(u for u in sampler.macro.units if u["geological_unit_id"]==data["parent_unit_id"])
            materialize_geological_unit(db,campaign_id,SurfacePoint(*parent["center"]))
            row = GenesisRegionalFormation(campaign_id=campaign_id,formation_id=identifier,parent_unit_id=data["parent_unit_id"],
                baseline=data,baseline_checksum=checksum(data),changes={})
            db.add(row)
            db.flush()
        _validate_formation(row,sampler)
        _parent_current(db,campaign_id,row,sampler)
        existing = _sources(db,campaign_id,row)
        if experimental_sources:
            if row.changes:
                raise ValueError("Changed JR1 formation requires event reconciliation")
            # No current exposure claim survives an uninterpreted T1 event at the anchor.
            query_altitude(db,campaign_id,SurfacePoint(*row.baseline["anchor_point"]))
            proposals = select_sources(row.baseline,sampler.signature,policy)
            by_id = {r.deposit_id:r for r in existing}
            if not set(by_id)<={p["deposit_id"] for p in proposals}:
                raise ValueError("JR1 existing sources conflict with pinned policy")
            for proposal in proposals:
                baseline = {**proposal,"eligible_not_instantiated":False,"state":"experimental_instantiated"}
                if proposal["deposit_id"] in by_id:
                    if by_id[proposal["deposit_id"]].baseline!=baseline:
                        raise ValueError("Established JR1 source cannot be reinterpreted")
                    continue
                source = GenesisMineralDeposit(campaign_id=campaign_id,deposit_id=proposal["deposit_id"],unit_id=row.parent_unit_id,
                    baseline=baseline,baseline_checksum=checksum(baseline),remaining_units=proposal["initial_volume_units"])
                db.add(source)
                db.flush()
                db.add(GenesisRegionalSource(campaign_id=campaign_id,deposit_id=source.deposit_id,
                    formation_id=row.formation_id,material_id=proposal["material_id"]))
            db.flush()
        return row


def query_regional_geology(db,campaign_id,point,*,baseline_only=False):
    if type(baseline_only) is not bool:
        raise ValueError("Explicit event policy required")
    _,sampler,_ = context(db,campaign_id)
    _,_,_,identifier = sampler.address(point)
    row = db.get(GenesisRegionalFormation,(campaign_id,identifier))
    if row is not None and row not in db.dirty:
        db.refresh(row)
    if row is None:
        raise ValueError("Formation not materialized; query does not generate geology or deposits")
    _validate_formation(row,sampler)
    _parent_current(db,campaign_id,row,sampler,baseline_only)
    if row.changes and not baseline_only:
        raise ValueError("JR1 event overlay required; baseline_only is diagnostic")
    if not baseline_only:
        query_altitude(db,campaign_id,SurfacePoint(*row.baseline["anchor_point"]))
    sources = _sources(db,campaign_id,row)
    return {"formation":deepcopy(row.baseline),"opportunities":opportunities(row.baseline,sampler.signature),
        "sources":[{"deposit_id":r.deposit_id,"remaining_units":r.remaining_units,"baseline":deepcopy(r.baseline)} for r in sources],
        "baseline_only":baseline_only,"access_authorized":False,"generated_by_query":False}
