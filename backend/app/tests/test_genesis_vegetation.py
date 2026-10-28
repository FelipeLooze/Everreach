from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json,os,subprocess,sys
from pathlib import Path
import pytest
from app.game.world.genesis.vegetation.catalog import load_flora_catalog
from app.game.world.genesis.vegetation.config import VegetationConfig
from app.game.world.genesis.vegetation.field import VegetationSampler,eligibility
from app.game.world.genesis.terrain.address import point_on_face
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.sphere_topology import SurfacePoint,CellKey,cell_center
from app.game.world.genesis.geology.regional.experiment import window_point
from scripts.validate_vegetation import inputs_vg1,centers


@pytest.fixture(scope="module")
def vegetation():
    return inputs_vg1(42)


def test_single_authority_integrity_and_compiled_immutability():
    c=load_flora_catalog()
    assert len(c.species)==3096 and c.part_count==c.item_count==6192 and len(c.by_habitat)==100
    assert len({p['item_id'] for s in c.species.values() for p in s.parts()})==6192
    assert sum(s.extreme_json is not None for s in c.species.values())==96
    assert sum(s.kind=="consorcio_simbiotico" for s in c.species.values())==34
    with pytest.raises(TypeError):c.species["fake"]=None
    s=c.species["EV-FL-0001"];parts=s.parts();parts[0]["item_id"]="fake"
    assert s.parts()[0]["item_id"]=="IT-EVR-FL-0001-P01"


def test_eight_legacy_overlays_remain_conditional():
    c=load_flora_catalog();overlays=json.loads(c.overlays_json)
    assert len(overlays)==8
    for o in overlays:
        assert o["ambiente_completo_nao_e_habitat_automatico"]
        assert o["restricao_microhabitat_obrigatoria"]
        assert o["nao_altera_perfil_ecologico_legado"]


@pytest.mark.parametrize("sid",[f"EV-FL-{i:04d}" for i in range(3001,3097,6)])
def test_extremes_are_pending_without_specific_microhabitat_and_energy(vegetation,sid):
    e=vegetation.environment.sample(centers(42)["moderate"])
    state,why=eligibility(vegetation.catalog.species[sid],e,vegetation.water_facts(centers(42)["moderate"]))
    assert state=="pending" and why


def test_exceptional_requires_exact_source_even_if_other_filters_pass(vegetation):
    sp=next(s for s in vegetation.catalog.species.values() if s.magic=="excepcional")
    state,why=eligibility(sp,{},{} )
    assert state=="pending" and str(sp.anomaly) in why[0]


def eligible_case(v):
    p=centers(42)["moderate"];e=v.environment.sample(p);w=v.water_facts(p)
    sp=next(s for s in v.catalog.species.values() if eligibility(s,e,w)[0]=="eligible")
    return sp,e,w


def test_unknown_is_not_zero_or_favorable_and_runoff_is_not_required(vegetation):
    s,e,w=eligible_case(vegetation)
    assert eligibility(s,e,{**w,"local_runoff_mm":0})[0]=="eligible"
    assert eligibility(replace(s,temperature=None),e,w)[0]=="pending"
    missing=deepcopy(e);missing["logical_facts"]["clima.indice_aridez"]=None
    assert eligibility(s,missing,w)[0]=="pending"
    assert eligibility(s,e,{**w,"ET_mm":None})[0]=="pending"
    assert eligibility(s,e,{**w,"ET_mm":0})[0]=="incompatible"
    missing=deepcopy(e);missing["physical_inputs"]["substrates"]=[]
    assert eligibility(s,missing,w)[0]=="pending"


@pytest.mark.parametrize("kind",["alga","junco","fungo","trepadeira","consorcio_simbiotico"])
def test_water_energy_and_support_not_invented(vegetation,kind):
    s,e,w=eligible_case(vegetation)
    assert eligibility(replace(s,kind=kind),e,w)[0]=="pending"


@pytest.mark.parametrize("seed",[42,0,7,2026,12345])
def test_real_finite_founders_and_source_preservation(seed):
    v=inputs_vg1(seed);before=checksum(v.environment.climate.to_dict()),checksum(v.water.to_dict())
    samples=[v.sample(p) for p in centers(seed).values()]
    assert any(s["established"] for s in samples)
    for sample in samples:
        assert sum(p["cover_ppm"] for p in sample["populations"])==sample["cover_ppm"]
        assert 0<=sample["cover_ppm"]<=sample["ecological_cover_ceiling_ppm"]<=1000000
        assert sample["individuals_materialized"]==0
        for pop in sample["populations"]:
            assert pop["founder_count"]>0 and pop["origin"]=="pre_player_biogeographic_history_v1"
            sp=v.catalog.species[pop["species_id"]]
            assert sp.magic!="excepcional" and sp.extreme_json is None
            p=SurfacePoint(*sample["point"])
            assert eligibility(sp,v.environment.sample(p),v.water_facts(p))[0]=="eligible"
    assert before==(checksum(v.environment.climate.to_dict()),checksum(v.water.to_dict()))


def test_order_lod_same_patch_and_bounded_cache(vegetation):
    v=vegetation;points=[cell_center(CellKey(0,4,x,8)) for x in range(16)]
    a=[v.sample(p) for p in points];v.cache.clear()
    b=list(reversed([v.sample(p) for p in reversed(points)]))
    assert a==b
    for p,s in zip(points,a):
        patch,_=v.address(p)
        assert v.sample(patch.point(1,1,2))==s
    assert len(v.cache)<=128


def test_face_edge_and_corner_aliases_and_smooth_range_field(vegetation):
    v=vegetation
    # +X east is +Y west. Canonical ray normalization removes chart ownership.
    a=point_on_face(0,100,51,100);b=point_on_face(2,0,51,100)
    assert a==b and v.sample(a)==v.sample(b)
    corners=[point_on_face(face,u,w,1) for face in range(6) for u in (0,1) for w in (0,1)]
    groups={}
    for p in corners:
        sig=checksum(v.sample(p));assert groups.setdefault(p.xyz,sig)==sig
    left=SurfacePoint(10**9,10**9-1,20000000);right=SurfacePoint(10**9-1,10**9,20000000)
    assert abs(v._field(left,4000,"continuity")-v._field(right,4000,"continuity"))<5


def test_game_direction_changes_composition_without_broadening_eligibility(vegetation):
    baseline=vegetation;directed=VegetationSampler(baseline.environment,baseline.water,VegetationConfig(policy="exploration_mosaic_v1"))
    center=centers(42)["moderate"]
    pts=[window_point(center,250*(i-10),0,baseline.radius) for i in range(21)]
    a=[baseline.sample(p) for p in pts];b=[directed.sample(p) for p in pts]
    assert len({x["dominant_species"] for x in b})>len({x["dominant_species"] for x in a})
    assert max(s["cover_ppm"] for s in b)-min(s["cover_ppm"] for s in b)>max(s["cover_ppm"] for s in a)-min(s["cover_ppm"] for s in a)
    for s in b:
        p=SurfacePoint(*s["point"])
        for pop in s["populations"]:
            assert eligibility(directed.catalog.species[pop["species_id"]],directed.environment.sample(p),directed.water_facts(p))[0]=="eligible"
    assert baseline.environment.signature==directed.environment.signature
    assert baseline.water.signature==directed.water.signature
    assert baseline.signature!=directed.signature


def test_between_process_determinism(vegetation):
    code="from scripts.validate_vegetation import inputs_vg1,centers;from app.game.world.genesis.terrain.field import checksum;print(checksum(inputs_vg1(42).sample(centers(42)['moderate'])))"
    expected=checksum(vegetation.sample(centers(42)["moderate"]))
    env=dict(os.environ,PYTHONHASHSEED="971")
    output=subprocess.check_output([sys.executable,"-c",code],cwd=Path(__file__).resolve().parents[2],env=env,text=True)
    assert output.strip()==expected


def test_reject_c2_without_header_conversion(vegetation):
    from app.game.world.genesis.water.config import WaterConfig
    from app.game.world.genesis.climate.v2 import ClimateConfigV2
    from app.game.world.genesis.water.config import check_climate_contract
    with pytest.raises(ValueError):check_climate_contract(WaterConfig(),vegetation.environment.climate.config)
    with pytest.raises(ValueError):check_climate_contract(vegetation.water.config,ClimateConfigV2())


@pytest.mark.parametrize("radius",[6371000,63710000,254840000,10**12])
def test_physical_patch_resolution_and_area_at_giant_radii(radius):
    from app.game.world.genesis.terrain.address import level_for_spacing,tile_at
    v=object.__new__(VegetationSampler);v.radius=radius
    level=level_for_spacing(radius,1000,1)
    a=tile_at(SurfacePoint(1000000,200000,300000),level)
    area=v._patch_area(a)
    assert 10000<area<=1000000
    assert a.level>0 and a.point(1,1,2)==SurfacePoint(*a.point(1,1,2).xyz)


@pytest.mark.parametrize("bad",[True,False,2,"1"])
def test_explicit_vegetation_version_required(bad):
    with pytest.raises(ValueError):VegetationConfig(vegetation_version=bad)
