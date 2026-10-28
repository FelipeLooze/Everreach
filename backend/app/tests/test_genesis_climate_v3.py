from copy import deepcopy
from math import exp
import json
import os
import subprocess
import sys
import pytest
from app.game.world.genesis.climate.v3 import (ClimateConfigV3,exp_negative,rain_fraction,
    recycled_transport,validate_accounting)
from app.game.world.genesis.climate.geometry import Q,geometry,unit
from app.game.world.genesis.climate.dispatch import parse_climate_config
from app.game.world.genesis.climate.plan import _solve_climate,load_climate_plan
from app.game.world.genesis.climate.query import sample_climate
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.environment.adapter import EnvironmentSampler
from app.game.world.genesis.environment.config import EnvironmentConfigC3,parse_environment_config
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.formation_config import plate_scale_m
from scripts.validate_environment import environment_inputs,import_sources
from scripts.compare_climate_versions import solve


@pytest.fixture(scope='module')
def reference():
    old=environment_inputs(42,63710000)
    new=solve(old.climate,ClimateConfigV3())
    return old,new


@pytest.mark.parametrize('tau',[0,1000,50000,250000,1000000,3000000,15000000,20000000])
def test_fixed_optical_depth_and_subdivision(tau):
    value=exp_negative(tau)
    assert 0<=value<=Q and abs(value-round(exp(-tau/Q)*Q))<60
    half=exp_negative(tau//2)
    assert abs(value-half*half//Q)<60


def test_rise_and_distance_exposure_compose_without_per_cell_rain_multiplier():
    cfg=ClimateConfigV3();d=unit(SurfacePoint(1,0,1))
    full=rain_fraction(d,0,1000,2000000,3000000,cfg)
    half=rain_fraction(d,0,500,1000000,3000000,cfg)
    assert abs(Q-full-(Q-half)*(Q-half)//Q)<60
    assert rain_fraction(d,0,2000,2000000,3000000,cfg)>full


def test_recycling_needs_rain_and_is_limited_by_PET_and_gross_precipitation():
    stencils=(((0,1),),((0,1),),((1,1),),((2,1),))
    zero=recycled_transport(stencils,(Q,)*4,(300000,)*4,(0,)*4,(Q,)*4,64,650000)
    assert zero[0]==(0,)*4 and all(r[3]==r[4]==0 for r in zero[1])
    args=(stencils,(Q,)*4,(300000,)*4,(Q,0,0,0),(0,10000,Q,0),64,450000)
    forward=recycled_transport(*args)
    assert forward==recycled_transport(*args,node_order=(3,2,1,0))
    for i,r in enumerate(forward[1]):
        incoming,loss,available,gross,recycled,outgoing,cap=r
        assert recycled<=min(cap,gross*450000//Q)
        if i:assert incoming==loss+available and available+recycled==gross+outgoing
    assert forward[1][1][4]==10000 and forward[1][3][4]==0
    dry=recycled_transport(*args[:-1],0)
    assert forward[1][3][3]>dry[1][3][3]


def test_C3_preserves_windward_rain_and_lee_shadow_with_recycling():
    cfg=ClimateConfigV3();d=unit(SurfacePoint(1,0,1))
    flat=rain_fraction(d,0,0,3000000,3000000,cfg)
    ridge=rain_fraction(d,0,2500,3000000,3000000,cfg)
    stencils=(((0,1),),((0,1),),((1,1),),((2,1),))
    a=recycled_transport(stencils,(950000,)*4,(flat,)*4,(Q,0,0,0),(Q,)*4,64,450000)
    b=recycled_transport(stencils,(950000,)*4,(flat,flat,ridge,flat),(Q,0,0,0),(Q,)*4,64,450000)
    assert b[1][2][3]>a[1][2][3] and b[1][3][3]<a[1][3][3]


def test_C3_is_explicit_and_C2_replays_unchanged(reference):
    old,new=reference;before=checksum(old.climate.to_dict())
    assert parse_climate_config(new.config.model_dump())==new.config
    assert solve(old.climate,old.climate.config)==old.climate
    assert checksum(old.climate.to_dict())==before
    for name in ('heights','marine','sea_temperature_centi_c','insolation_ppm','wind_milli_m_s','maritime_ppm'):
        assert getattr(new,name)==getattr(old.climate,name)
    with pytest.raises(ValueError):EnvironmentSampler(old.regional,old.h1,new)
    env=EnvironmentSampler(old.regional,old.h1,new,EnvironmentConfigC3())
    sample=env.sample(SurfacePoint(1,0,0))
    assert 'C3' in sample['provenance'] and 'C3_seasons' in sample['physical_inputs']
    assert 'C2_seasons' not in sample['physical_inputs']
    assert parse_environment_config(env.config.model_dump())==env.config


def test_ledger_roundtrip_rejects_corruption_without_solver(reference):
    old,new=reference;payload=json.loads(json.dumps(new.to_dict()))
    loaded=load_climate_plan(payload,new.source_signature,new.hydrology_signature,new.radius_m,new.sea_level_m)
    assert loaded==new;validate_accounting(loaded)
    for corruption in ('budget','rain','length','PET_cap'):
        data=deepcopy(payload)
        if corruption=='budget':data['accounting'][0][0][4]+=Q
        elif corruption=='rain':data['precipitation_mm'][0][0]+=1
        elif corruption=='length':data['condensation_length_m']+=1
        else:data['accounting'][0][0][6]+=1
        with pytest.raises(ValueError):load_climate_plan(data,new.source_signature,new.hydrology_signature,new.radius_m,new.sea_level_m)


@pytest.mark.parametrize('point',[SurfacePoint(1,1,0),SurfacePoint(1,1,1),SurfacePoint(0,0,1),SurfacePoint(0,0,-1)])
def test_C3_seams_poles_and_seasonal_contract(reference,point):
    _,plan=reference;a=sample_climate(plan,point)
    for delta in ((1,0,0),(0,1,0),(0,0,1)):
        b=sample_climate(plan,SurfacePoint(*(2**28*v+d for v,d in zip(point.xyz,delta))))
        assert abs(a['annual_precipitation_mm']-b['annual_precipitation_mm'])<=4
        assert abs(a['mean_temperature_centi_c']-b['mean_temperature_centi_c'])<=2
    assert a['annual_precipitation_mm']==sum(s['precipitation_mm'] for s in a['seasons'])
    assert a['runoff_mm'] is a['permanent_water'] is None


@pytest.mark.parametrize('radius',[6371000,63710000,637100000,10**12])
def test_radius_and_extreme_energy_limits_never_invent_water(radius):
    cfg=ClimateConfigV3(level=3,radiative_offset_centi_c=-15000);n=len(geometry(3).points)
    p=_solve_climate('source','h1',radius,0,(100,)*n,(False,)*n,plate_scale_m(radius),cfg)
    assert all(v==0 for s in p.precipitation_mm for v in s)
    assert all(r[4]==0 for s in p.accounting for r in s)


def test_hydrology_does_not_reuse_C2_balance_as_C3(reference):
    from app.game.world.genesis.water.config import WaterConfig
    from app.game.world.genesis.water.plan import build_water_plan,load_water_plan
    old,new=reference;source=old.regional.terrain.plan.source
    with pytest.raises(ValueError):WaterConfig(source_climate_version=3)
    with pytest.raises(ValueError):build_water_plan(source,old.h1,new)
    water=build_water_plan(source,old.h1,old.climate)
    with pytest.raises(ValueError,match='provenance'):load_water_plan(water.to_dict(),old.h1,new,water.hr_signature)


def test_C3_and_C2_campaigns_coexist_and_E1_profile_is_pinned(db_session,reference,monkeypatch):
    from app.game.world.genesis.climate.service import (get_climate_plan,clear_climate_cache,initialize_climate,materialize_climate_sector)
    from app.game.world.genesis.environment.service import (initialize_environment,materialize_environment_point,query_environment,clear_environment_cache)
    from app.game.world.genesis.sphere_topology import cell_at
    old,new=reference;experimental=EnvironmentSampler(old.regional,old.h1,new,EnvironmentConfigC3())
    c2id=import_sources(db_session,old,42);c3id=import_sources(db_session,experimental,42)
    with pytest.raises(ValueError):initialize_climate(db_session,c2id,new.config)
    with pytest.raises(ValueError):initialize_environment(db_session,c3id)
    initialize_environment(db_session,c3id,experimental.config)
    p=SurfacePoint(8,5,-7);row=materialize_environment_point(db_session,c3id,p);baseline=deepcopy(row.baseline)
    key=cell_at(p,old.regional.terrain.plan.source.config.sector_level)
    sector=materialize_climate_sector(db_session,c3id,key);saved=deepcopy(sector.baseline)
    db_session.commit();db_session.expire_all();clear_climate_cache();clear_environment_cache()
    def cannot_regenerate(*args,**kwargs):raise AssertionError('Persisted climate/environment was regenerated')
    monkeypatch.setattr('app.game.world.genesis.climate.service.build_climate_plan',cannot_regenerate)
    monkeypatch.setattr(EnvironmentSampler,'sample',cannot_regenerate)
    assert get_climate_plan(db_session,c2id)==old.climate and get_climate_plan(db_session,c3id)==new
    assert materialize_climate_sector(db_session,c3id,key).baseline==saved
    assert query_environment(db_session,c3id,p)['baseline']==baseline
    assert materialize_environment_point(db_session,c3id,p).baseline==baseline


def test_process_hash_randomization_does_not_change_C3():
    code='''from app.game.world.genesis.climate.plan import _solve_climate
from app.game.world.genesis.climate.v3 import ClimateConfigV3
from app.game.world.genesis.climate.geometry import geometry
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.formation_config import plate_scale_m
c=ClimateConfigV3(level=3);g=geometry(3);h=tuple(-100 if p.xyz[0]<0 else 100 for p in g.points)
p=_solve_climate('source','h1',63710000,0,h,tuple(z<0 for z in h),plate_scale_m(63710000),c)
print(checksum(p.to_dict()))'''
    values=[subprocess.check_output([sys.executable,'-c',code],env={**os.environ,'PYTHONHASHSEED':s},text=True) for s in ('3','123')]
    assert values[0]==values[1]
