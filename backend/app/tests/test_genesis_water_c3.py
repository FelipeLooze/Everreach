from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import pytest
from sqlalchemy.orm import Session
from app.game.world.genesis.water.config import WaterConfig,WaterConfigC3R155,parse_water_config,C3_FORCING_CONTRACT
from app.game.world.genesis.water.balance import solve as solve_buckets
from app.game.world.genesis.water.plan import build_water_plan,load_water_plan,checksum,signature
from app.game.world.genesis.water.c3_forcing import attach
from app.game.world.genesis.water.service import initialize_water_balance,get_water_plan,clear_water_cache
from app.game.world.genesis.water_reconciliation.service import initialize_reconciliation,prepare_water_domain,get_water_domain,reconcile,get_revision
from app.game.world.genesis.water_reconciliation.sources import clear_baseline_cache
from app.game.world.genesis.water_reconciliation.practical.service import initialize_practical_hydrology,prepare_natural_passage,get_local_account
from app.game.world.genesis.water_reconciliation.practical.config import PracticalConfig
from app.game.world.genesis.water_reconciliation.practical.proof import inspect_parcel
from app.game.world.genesis.terrain.address import TerrainTile
from scripts.validate_water_c3 import inputs,fixed_evidence,import_disposable,requests
from scripts.validate_environment import import_sources
from app.tests.test_genesis_practical_hydrology_persistence import flow_request

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(scope='module')
def physical():
    old,new=inputs(42);source=new.regional.terrain.plan.source
    water=build_water_plan(source,new.h1,new.climate,config=WaterConfigC3R155())
    old_data=json.loads((ROOT/'artifacts/water-w1/seed-42-r63710000/plan.json').read_text())
    legacy=load_water_plan(old_data,old.h1,old.climate,old_data['hr_signature'])
    historical=json.loads((ROOT/'artifacts/practical-hydrology-p1/probe.json').read_text())['found']
    config=PracticalConfig.model_validate(historical['config'])
    proof,_=inspect_parcel(water,new.regional.terrain,TerrainTile(*historical['allocation']['tile']),config)
    assert proof is not None
    return old,new,water,legacy,proof


def prepare(db,physical):
    _,sampler,water,_,proof=physical;cid,row=import_disposable(db,sampler,water,[])
    initialize_reconciliation(db,cid,cutover_minute=0)
    initialize_practical_hydrology(db,cid,PracticalConfig.model_validate(proof['config']))
    evidence=prepare_natural_passage(db,cid,proof);prepare_water_domain(db,cid,evidence.node)
    return cid,row,proof,evidence


def test_forcing_configuration_is_explicit_and_preserves_legacy_dump():
    old=WaterConfig();assert 'forcing_contract' not in old.model_dump()
    with pytest.raises(ValueError):WaterConfig(source_climate_version=3)
    new=WaterConfigC3R155();assert parse_water_config(new.model_dump())==new
    assert new.water_version==1 and new.forcing_contract==C3_FORCING_CONTRACT
    assert parse_water_config(old.model_dump())==old


@pytest.mark.parametrize('data',[{'source_climate_version':3},{'source_climate_version':3,'forcing_contract':'guess'},
    {'source_climate_version':True,'forcing_contract':C3_FORCING_CONTRACT}])
def test_unknown_or_implicit_contract_is_not_converted(data):
    with pytest.raises(ValueError):parse_water_config(data)


def test_gross_rain_total_PET_avoids_both_double_subtraction_and_double_credit():
    cfg=WaterConfigC3R155(warmup_years=0,soil_capacity_mm=0,surface_capacity_mm=0)
    def result(p,e):
        return solve_buckets((1,),(False,),(-1,),(0,),((p,),)*4,((e,),)*4,((0,),)*4,((2000,),)*4,
            (0,),(False,),(0,),360,cfg)
    correct=result(100,60);double_loss=result(60,60);double_credit=result(140,60)
    assert correct.periods[0]['stores']['unresolved'][0]==40
    assert correct.periods[0]['fluxes']['evapotranspiration'][0]==60
    assert double_loss.periods[0]['stores']['unresolved'][0]==0
    assert double_credit.periods[0]['stores']['unresolved'][0]==80
    dry=result(0,60)
    assert all(p['totals']['end_storage']==p['totals']['evapotranspiration']==0 for p in dry.periods)


def test_real_forcing_never_nets_or_recredits_recycling(physical):
    old,new,water,legacy,_=physical
    assert water.precipitation_mm!=legacy.precipitation_mm
    for p,r,n in zip(water.precipitation_mm,water.atmospheric_recycling_mm,water.atmospheric_net_deposition_mm):
        assert all(a==b+c and 0<=b<=a for a,b,c in zip(p,r,n))
    assert all(p['totals']['residual_liters']==0 for p in water.solution.periods)
    assert all(p['fluxes']['evapotranspiration'][i]<=p['fluxes']['pet'][i] for p in water.solution.periods for i in range(len(water.hydrology.heights)))
    assert water.to_dict()['atmospheric_return_credited_to_stocks'] is False
    from app.game.world.genesis.water.query import node_record
    gaps=[(s,i) for s,p in enumerate(water.solution.periods) for i,area in enumerate(water.hydrology.cell_area_m2)
        if not water.hydrology.drainage.marine[i] and water.atmospheric_recycling_mm[s][i]*area>p['fluxes']['evapotranspiration'][i]]
    assert gaps  # Native atmospheric hypotheses need not equal surface bucket ET.
    s,i=gaps[0];view=node_record(water,i)['periods'][s]
    assert view['model_ET_shortfall_to_atmospheric_hypothesis_liters']>0
    assert view['atmospheric_recycling_credited_to_stock'] is False
    assert any(sum(row[i] for row in water.precipitation_mm)>=sum(row[i] for row in water.pet_mm)>0 and
        sum(p['fluxes']['local_runoff'][i] for p in water.solution.periods)==0
        for i in range(len(water.hydrology.heights)) if not water.hydrology.drainage.marine[i])
    saved=json.loads((ROOT/'artifacts/water-w1/seed-42-r63710000/plan.json').read_text())
    assert json.loads(json.dumps(legacy.to_dict()))==saved


def test_C3_roundtrip_is_deterministic_without_hydrological_resolve(physical,monkeypatch):
    _,new,water,_,_=physical
    assert build_water_plan(new.regional.terrain.plan.source,new.h1,new.climate,config=water.config)==water
    payload=json.loads(json.dumps(water.to_dict()))
    def forbidden(*args,**kwargs):raise AssertionError('Unexpected balance re-solve')
    monkeypatch.setattr('app.game.world.genesis.water.plan.solve',forbidden)
    assert load_water_plan(payload,new.h1,new.climate,water.hr_signature)==water


@pytest.mark.parametrize('field',['atmospheric_recycling_mm','atmospheric_net_deposition_mm','climate_payload_checksum','forcing_contract'])
def test_corrupt_diagnostics_fail_closed(physical,field):
    _,new,water,_,_=physical;data=json.loads(json.dumps(water.to_dict()))
    if field.endswith('_mm'):data[field][0][0]+=1
    else:data[field]='changed'
    with pytest.raises(ValueError):load_water_plan(data,new.h1,new.climate,water.hr_signature)


def test_C2_cannot_be_relabelled_with_new_signature_or_new_diagnostic_header(physical):
    _,new,water,legacy,_=physical
    config=WaterConfigC3R155()
    forged=replace(legacy,config=config,climate_signature=new.climate.signature,
        signature=signature(new.h1.signature,new.climate.signature,legacy.hr_signature,config,legacy.manifest))
    forged=attach(forged,new.climate)
    with pytest.raises(ValueError):load_water_plan(forged.to_dict(),new.h1,new.climate,legacy.hr_signature)
    with pytest.raises(ValueError):load_water_plan(water.to_dict(),new.h1,physical[0].climate,water.hr_signature)


def test_only_adopted_R1_55_profile_is_admitted(physical):
    from scripts.compare_climate_versions import solve
    from app.game.world.genesis.climate.v3 import ClimateConfigV3,ClimateConfigV3R1
    _,new,_,_,_=physical
    for cfg in (ClimateConfigV3(land_recycling_ppm=550000),ClimateConfigV3R1(land_recycling_ppm=450000)):
        other=solve(new.climate,cfg)
        with pytest.raises(ValueError,match='R1-55'):build_water_plan(new.regional.terrain.plan.source,new.h1,other,config=WaterConfigC3R155())


def test_initialization_is_explicit_and_no_legacy_reconfiguration(db_session,physical):
    old,new,water,legacy,_=physical;cid=import_sources(db_session,new,42)
    from app.game.world.genesis.hydrology.regional_service import initialize_regional_hydrology
    from app.db.models.world_water import GenesisWaterPlan
    initialize_regional_hydrology(db_session,cid)
    with pytest.raises(ValueError):initialize_water_balance(db_session,cid)
    assert db_session.get(GenesisWaterPlan,cid) is None
    row=initialize_water_balance(db_session,cid,WaterConfigC3R155());assert row.signature==water.signature
    regions,_=fixed_evidence(old,42);oldcid,_=import_disposable(db_session,old,legacy,regions)
    with pytest.raises(ValueError,match='silently'):initialize_water_balance(db_session,oldcid,WaterConfigC3R155())
    assert get_water_plan(db_session,oldcid)==legacy


def test_W2_P1_real_positive_flow_closes_same_parent_and_finite_children(db_session,physical):
    cid,row,proof,evidence=prepare(db_session,physical)
    from app.db.models.world_water_reconciliation import GenesisWaterReconciliation
    sources=db_session.get(GenesisWaterReconciliation,cid).sources
    assert sources['climate_version']==3 and sources['climate_forcing_contract']==C3_FORCING_CONTRACT and 'c2_signature' not in sources
    original=get_water_domain(db_session,cid,evidence.node);checksum_before=checksum(row.plan)
    request=requests(db_session,cid,proof,evidence);allocated=reconcile(db_session,cid,request)
    assert reconcile(db_session,cid,request).revision_id==allocated.revision_id
    flow=flow_request(db_session,cid,proof,evidence)
    moved=reconcile(db_session,cid,flow);assert moved.payload['local_reconciliation']['delivered_liters']>0
    assert moved.payload['local_reconciliation']['residual_liters']==0
    assert reconcile(db_session,cid,flow).revision_id==moved.revision_id
    current=get_water_domain(db_session,cid,evidence.node)
    assert sum(original['state']['accounts'].values())==sum(current['state']['accounts'].values())
    assert checksum(row.plan)==checksum_before
    with pytest.raises(ValueError):reconcile(db_session,cid,requests(db_session,cid,proof,evidence).model_copy(update={'operation_id':'claim-again'}))
    with pytest.raises(ValueError):reconcile(db_session,cid,flow_request(db_session,cid,proof,evidence,'repeat-episode'))


def test_reopen_revisit_and_rollback_preserve_C3_authority_without_regeneration(db_session,physical,monkeypatch):
    cid,row,proof,evidence=prepare(db_session,physical);reconcile(db_session,cid,requests(db_session,cid,proof,evidence))
    flow=flow_request(db_session,cid,proof,evidence);key=evidence.baseline['target_account'];before=get_local_account(db_session,cid,key)['liters']
    db_session.commit();clear_water_cache();clear_baseline_cache()
    def forbidden(*args,**kwargs):raise AssertionError('Unexpected solve/terrain regeneration')
    monkeypatch.setattr('app.game.world.genesis.water.plan.solve',forbidden)
    monkeypatch.setattr('app.game.world.genesis.water.service.build_water_plan',forbidden)
    monkeypatch.setattr('app.game.world.genesis.terrain.field.TerrainSampler.sample',forbidden)
    with Session(db_session.get_bind()) as db:
        moved=reconcile(db,cid,flow);rid=moved.revision_id;db.rollback()
    with Session(db_session.get_bind()) as db:
        assert get_local_account(db,cid,key)['liters']==before
        moved=reconcile(db,cid,flow);rid=moved.revision_id;payload=deepcopy(moved.payload);db.commit()
    with Session(db_session.get_bind()) as db:
        assert get_revision(db,cid,rid)['payload']==payload and reconcile(db,cid,flow).revision_id==rid


def test_future_proposal_has_no_recycling_credit_or_historical_flux_recredit(physical):
    from app.game.world.genesis.water_reconciliation.practical.future import future_forcing_proposal
    _,_,water,_,proof=physical
    proposal=future_forcing_proposal(water,TerrainTile(*proof['allocation']['tile']),PracticalConfig.model_validate(proof['config']),cutover_minute=0,cycle=0,period=0)
    assert proposal['credit_authorized'] is proposal['historical_W1_flux_recredited'] is proposal['atmospheric_recycling_credit'] is False
    assert proposal['climate_forcing_contract']==C3_FORCING_CONTRACT
