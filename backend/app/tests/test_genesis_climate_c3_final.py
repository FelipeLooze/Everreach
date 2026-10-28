from copy import deepcopy
import json
from math import log1p
from pathlib import Path
import pytest
from app.game.world.genesis.climate.v3 import (ClimateConfigV3,ClimateConfigV3R1,
    exp_negative,fraction_optical_depth,rain_fraction)
from app.game.world.genesis.climate.dispatch import parse_climate_config
from app.game.world.genesis.climate.plan import load_climate_plan,_solve_climate
from app.game.world.genesis.climate.geometry import Q,unit,geometry
from app.game.world.genesis.sphere_topology import CellKey,cell_center,neighbor,SurfacePoint
from app.game.world.genesis.sphere_area import cell_solid_angle
from app.game.world.genesis.formation_config import plate_scale_m
from app.game.world.genesis.environment.adapter import EnvironmentSampler
from app.game.world.genesis.environment.config import EnvironmentConfigC3
from scripts.finalize_climate_c3 import cross_matrix,sampled_components,favorable,warm_humid
from scripts.validate_environment import environment_inputs,import_sources
from scripts.compare_climate_versions import solve

ROOT=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('fraction',[0,50000,150000,250000,350000,500000,850000])
def test_fraction_has_correct_optical_meaning_at_reference_exposure(fraction):
    tau=fraction_optical_depth(fraction)
    assert abs(tau-round(-log1p(-fraction/Q)*Q))<=2
    assert abs(Q-exp_negative(tau)-fraction)<60


def test_optical_profile_remains_composable_and_old_fraction_model_is_unchanged():
    old=ClimateConfigV3();new=ClimateConfigV3R1();d=unit(SurfacePoint(1,0,0))
    legacy=rain_fraction(d,0,0,3000000,3000000,old)
    corrected=rain_fraction(d,0,0,3000000,3000000,new)
    assert legacy==Q-exp_negative(350000)
    assert abs(corrected-350000)<60 and corrected>legacy
    full=rain_fraction(d,0,2000,3000000,3000000,new)
    half=rain_fraction(d,0,1000,1500000,3000000,new)
    assert abs((Q-full)-(Q-half)*(Q-half)//Q)<60


@pytest.mark.parametrize('bad',[-1,850001,True,1.5])
def test_optical_conversion_rejects_outside_calibrated_domain(bad):
    with pytest.raises(ValueError):fraction_optical_depth(bad)


def test_configuration_dispatch_is_explicit_without_changing_old_dumps():
    assert 'condensation_profile' not in ClimateConfigV3().model_dump()
    config=ClimateConfigV3R1(land_recycling_ppm=550000)
    assert type(parse_climate_config(config.model_dump())) is ClimateConfigV3R1
    assert parse_climate_config(ClimateConfigV3().model_dump())==ClimateConfigV3()
    for profile in (None,'unknown',True):
        with pytest.raises(ValueError):parse_climate_config({'climate_version':3,'condensation_profile':profile})


def sample(key,*,p=.7,t=8,primary='EV-BIO-FLORESTA_BOREAL',eligible=None):
    return {'cell':[key.face,key.level,key.x,key.y],'point':list(cell_center(key).xyz),
        'solid_angle':cell_solid_angle(key),'land':True,'P_over_PET':p,'rain_mm':300,'temperature_c':t,
        'primary_potential':primary,'eligible':eligible if eligible is not None else [primary]}


def test_matrix_separates_polar_desert_overlap_from_hydrological_aridity():
    rows=[sample(CellKey(0,5,0,0),p=None,t=-20,primary='EV-BIO-DESERTO_POLAR'),
        sample(CellKey(0,5,15,15),p=.6,primary='EV-BIO-ESTEPE',eligible=['EV-BIO-ESTEPE','EV-BIO-FLORESTA_BOREAL']),
        sample(CellKey(0,5,20,15),p=.01,primary='EV-BIO-DESERTO_PEDREGOSO')]
    m=cross_matrix(rows)
    assert sum(r['land_area_fraction'] for r in m['matrix'])==pytest.approx(1)
    assert set(m['dry_primary_area_by_ratio'])=={'PET0','moderate','hyperarid'}
    assert m['dry_primary_with_forest_eligible_area_fraction']>0
    assert m['semantic_flags']=={}
    assert not warm_humid(rows[0]) and not favorable(rows[0])


def test_component_graph_crosses_real_cube_seam_without_area_duplication():
    a=CellKey(0,5,31,16);b=neighbor(a,'east')
    rows=[sample(a),sample(b),sample(CellKey(0,5,0,0),p=.01,primary='EV-BIO-DESERTO_FRIO')]
    c=sampled_components(rows)
    assert c['component_count']==1 and c['favorable_cells']==2
    assert len(c['components'][0]['faces'])==2
    assert c['components'][0]['solid_angle']==pytest.approx(sum(r['solid_angle'] for r in rows[:2]))
    assert c['components'][0]['extent_lower_bound_km']>0
    assert sampled_components(list(reversed(rows)))==c


@pytest.fixture(scope='module')
def reference():
    original=environment_inputs(42,63710000)
    data=json.loads((ROOT/'artifacts/climate-recalibration-0.9.1/seed-42/c3-plan.json').read_text())
    old=load_climate_plan(data,original.climate.source_signature,original.h1.signature,63710000,original.climate.sea_level_m)
    return original,old,solve(original.climate,ClimateConfigV3R1())


def test_old_C3_exact_replay_and_R1_roundtrip_preserve_geography(reference):
    original,old,new=reference
    assert solve(original.climate,old.config)==old
    assert type(old.config) is ClimateConfigV3 and old.signature!=new.signature
    for field in ('heights','marine','sea_temperature_centi_c','insolation_ppm','wind_milli_m_s'):
        assert getattr(old,field)==getattr(new,field)
    data=json.loads(json.dumps(new.to_dict()))
    assert load_climate_plan(data,new.source_signature,new.hydrology_signature,new.radius_m,new.sea_level_m)==new


def test_profile_persists_and_hydrology_still_rejects_it(db_session,reference,monkeypatch):
    from app.game.world.genesis.climate.service import get_climate_plan,clear_climate_cache
    from app.game.world.genesis.environment.service import initialize_environment,materialize_environment_point,query_environment,clear_environment_cache
    from app.game.world.genesis.water.plan import build_water_plan
    original,old,new=reference
    a=EnvironmentSampler(original.regional,original.h1,old,EnvironmentConfigC3())
    b=EnvironmentSampler(original.regional,original.h1,new,EnvironmentConfigC3())
    old_id=import_sources(db_session,a,42);new_id=import_sources(db_session,b,42)
    initialize_environment(db_session,new_id,b.config);p=SurfacePoint(8,5,-7)
    stored=deepcopy(materialize_environment_point(db_session,new_id,p).baseline)
    db_session.commit();db_session.expire_all();clear_climate_cache();clear_environment_cache()
    def fail(*args,**kwargs):raise AssertionError('Unexpected regeneration')
    monkeypatch.setattr('app.game.world.genesis.climate.service.build_climate_plan',fail)
    monkeypatch.setattr(EnvironmentSampler,'sample',fail)
    assert get_climate_plan(db_session,old_id)==old
    assert get_climate_plan(db_session,new_id)==new
    assert query_environment(db_session,new_id,p)['baseline']==stored
    with pytest.raises(ValueError):build_water_plan(original.regional.terrain.plan.source,original.h1,new)


def test_no_source_or_PET_does_not_create_recycled_water():
    cfg=ClimateConfigV3R1(level=3,radiative_offset_centi_c=-15000);n=len(geometry(3).points)
    p=_solve_climate('s','h',63710000,0,(100,)*n,(False,)*n,plate_scale_m(63710000),cfg)
    assert all(r[3]==r[4]==0 for s in p.accounting for r in s)
