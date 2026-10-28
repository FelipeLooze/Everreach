"""Audit mathematics and exact C2/E1 units without changing authoritative models."""
from math import pi

import pytest

from app.game.world.genesis.climate.geometry import Q, geometry
from app.game.world.genesis.climate.physics import declinations, lapse
from app.game.world.genesis.climate.plan import _solve_climate
from app.game.world.genesis.climate.query import sample_climate
from app.game.world.genesis.climate.v2 import ClimateConfigV2, condensation
from app.game.world.genesis.sphere_area import cell_solid_angle
from app.game.world.genesis.sphere_topology import CellKey
from scripts.audit_climate_after_e1 import Distribution, grouping_keys, point_record, weighted_quantile
from scripts.validate_environment import environment_inputs


def row(p=100, pet=100, weight=1):
    return {'solid_angle':weight,'rain_mm':p,'pet_mm':pet,'temperature_c':10,
        'P_over_PET':p/pet if pet else None,'states':{'elegivel':1,'candidato_pendente':99},
        'eligible':['potential'],'primary_potential':'potential','ecotone':False,
        'period_rain_mm':[p/4]*4,'period_temperature_c':[10]*4}


def test_weighted_statistics_are_not_point_counts_or_mean_of_ratios():
    d=Distribution();d.add(row(100,100,1));d.add(row(0,900,3));r=d.result()
    assert r['rain_mm']['mean']==25
    assert r['P_over_PET']['mean']==.25
    assert r['ratio_of_area_mean_P_to_area_mean_PET']==pytest.approx(1/28)
    assert sum(r['index_area_fractions'].values())==1
    assert sum(r['natural_state_area_fractions'].values())==1
    assert r['period_mean_rain_mm']==[6.25]*4
    assert weighted_quantile([(0,3),(100,1)],.5)==0


def test_undefined_PET_is_reported_as_energy_limited_and_excluded_from_ratio_mean():
    d=Distribution();d.add(row(100,0,3));d.add(row(100,100,1));r=d.result()
    assert r['P_over_PET']['defined_area_fraction']==.25
    assert r['P_over_PET']['mean']==1
    assert r['index_area_fractions']=={'energy_limited':.75,'humid':.25}
    assert 'arid' not in r['index_area_fractions']


@pytest.mark.parametrize('level',[3,5])
def test_exact_spherical_weights_cover_planet_and_do_not_overweight_corners(level):
    n=2**level
    assert sum(cell_solid_angle(CellKey(f,level,x,y)) for f in range(6) for y in range(n) for x in range(n))==pytest.approx(4*pi)
    assert cell_solid_angle(CellKey(0,level,n//2,n//2))>cell_solid_angle(CellKey(0,level,0,0))


def test_unknown_ocean_distance_cannot_become_coastal():
    r={'land':True,'latitude_degrees':-70,'ocean_distance_m':None,'mountain':True,'height_m':3000}
    assert 'ocean_distance/unknown' in grouping_keys(r)
    assert 'latitude/land/60-75' in grouping_keys(r)
    assert 'relief/mountain_context' in grouping_keys(r)


def test_C2_annual_mm_are_sum_of_four_periods_with_correct_day_conversion():
    cfg=ClimateConfigV2(level=3);g=geometry(3);count=len(g.points)
    plan=_solve_climate('audit-source','audit-ocean',63710000,0,(-1,)*count,(True,)*count,12000000,cfg)
    i=count//2
    for s,dec in enumerate(declinations(cfg)):
        t=lapse(plan.sea_temperature_centi_c[s][i],0,cfg)
        supply=min(Q,max(150000,250000+max(0,t+1000)*150))
        if t<0:supply=supply*max(100000,Q+t*200)//Q
        rain_index=supply*condensation(g.directions[i],dec,0,cfg)//Q
        expected=rain_index*cfg.rain_scale_milli_mm_per_day*cfg.year_days//(Q*4000)
        assert plan.precipitation_mm[s][i]==expected
    sample=sample_climate(plan,g.points[i])
    assert sample['annual_precipitation_mm']==sum(plan.precipitation_mm[s][i] for s in range(4))
    assert sample['period_duration_days']==[360,4]
    assert sample['runoff_mm'] is sample['permanent_water'] is None


def test_real_E1_bridge_is_exact_without_rainfall_rescaling_or_runoff_inference():
    sampler=environment_inputs(42,63710000)
    before=sampler.climate.to_dict()
    for key in (CellKey(0,3,0,0),CellKey(0,3,1,0),CellKey(4,3,3,3),CellKey(5,3,3,3)):
        r=point_record(sampler,key)
        assert r['rain_mm']==sum(r['period_rain_mm'])
        assert sum(r['states'].values())==100
    assert sampler.climate.to_dict()==before
