from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import pytest
from app.game.world.genesis.geology.regional.config import RegionalConfig,RegionalPolicy
from app.game.world.genesis.geology.regional.field import RegionalSampler,adapt_formation
from app.game.world.genesis.geology.regional.spatial import PhysicalSites,position_mm
from app.game.world.genesis.geology.regional.occurrence import opportunities,select_sources
from app.game.world.genesis.geology.regional.experiment import window_formations,window_point,cross_sector_points
from app.game.world.genesis.geology.catalog import load_catalog
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.terrain.address import point_on_face,tile_at
from app.game.world.genesis.terrain.field import checksum
from scripts.validate_regional_geology import inputs,land_windows


@pytest.fixture(scope="module")
def reference():
    sampler=inputs(42,63710000)
    center=land_windows(sampler)[0]
    forms,budget=window_formations(sampler,center)
    return sampler,center,forms


@pytest.mark.parametrize("radius",[1000,6371000,63710000,637100000,1000000000000])
def test_integer_sites_coverage_and_true_nearest_in_larger_halo(radius):
    sites=PhysicalSites(radius,8000,"test-JR1")
    from itertools import product
    for p in (SurfacePoint(1,1,0),SurfacePoint(0,0,1),SurfacePoint(-5,3,-7)):
        key,point=sites.nearest(p)
        xyz=position_mm(p,radius);site_xyz=position_mm(point,radius)
        minimum=sum((x-y)**2 for x,y in zip(xyz,site_xyz))
        owner=tuple(v//(sites.spacing*1000) for v in xyz)
        for offset in product(range(-5,6),repeat=3):
            candidate=tuple(k+d for k,d in zip(owner,offset));other=sites.site(candidate)
            if other is not None:
                pos=position_mm(other,radius)
                assert (sum((x-y)**2 for x,y in zip(xyz,pos)),candidate)>=(minimum,key)
                assert all(k*sites.spacing*1000-2<=v<=(k+1)*sites.spacing*1000+2 for k,v in zip(candidate,pos))
        assert max(map(abs,point.xyz))<=2**53
        assert len(sites.cache)<=4096


def test_macro_preserved_multiple_local_formations_and_real_resources(reference):
    sampler,center,forms=reference
    before=checksum(sampler.macro.to_dict())
    assert len(forms)==245
    assert len({f["parent_unit_id"] for f in forms.values()})==1
    assert len({tuple(f["substrates"]) for f in forms.values()})>=2
    catalog=load_catalog()
    assessed=[opportunities(f,sampler.signature,catalog) for f in forms.values()]
    assert sum(len(a["opportunities"]) for a in assessed)==1474
    selected=[d for f in forms.values() for d in select_sources(f,sampler.signature,catalog=catalog)]
    assert len(selected)==71
    assert sum(d["rarity"]=="comum" for d in selected)==57
    assert sum(d["material_id"]=="EV-GEO-FAN-0001" for d in selected)==12
    assert any(f["exposure"]["rock_outcrop_model"] for f in forms.values())
    assert any(not f["exposure"]["rock_outcrop_model"] for f in forms.values())
    assert before==checksum(sampler.macro.to_dict())


@pytest.mark.parametrize("radius",[6371000,63710000,637100000,1000000000000])
def test_seams_poles_and_physical_resolution_independent_of_radius(radius):
    sampler=inputs(42,radius)
    d=2**48
    for a,b in ((point_on_face(0,d,d//2,d),point_on_face(2,0,d//2,d)),):
        assert a==b
        assert sampler.formation(a)==sampler.formation(b)
        left=point_on_face(0,d-1,d//2,d);right=point_on_face(2,1,d//2,d)
        assert sampler.formation(left)["formation_id"]==sampler.formation(right)["formation_id"]
    for p in (SurfacePoint(0,0,1),SurfacePoint(0,0,-1)):
        assert sampler.formation(p)==sampler.formation(SurfacePoint(*(v*99 for v in p.xyz)))
    assert sampler.sites.spacing==8000
    assert len(sampler.cache)<=256 and len(sampler.sites.cache)<=4096


def test_sector_and_lod_witness_with_selected_finite_source(reference):
    sampler,center,forms=reference
    for f in forms.values():
        selected=select_sources(f,sampler.signature)
        if not selected:
            continue
        witness=cross_sector_points(sampler,f)
        if witness:
            break
    assert witness and witness[0]["sector"]!=witness[1]["sector"]
    for view in witness:
        p=SurfacePoint(*view["point"])
        for lod in (5,12,20,32):
            tile=tile_at(p,lod)
            assert tile.level==lod
            assert sampler.formation(p)["formation_id"]==f["formation_id"]
            assert select_sources(sampler.formation(p),sampler.signature)==selected


def test_order_reversal_eviction_and_formation_records_reproducible(reference):
    sampler,center,forms=reference
    independent=RegionalSampler(sampler.macro,sampler.terrain)
    for f in reversed(list(forms.values())):
        assert independent.formation(SurfacePoint(*f["anchor_point"]))==f
    original=sampler.formation(center)
    for i in range(320):
        independent.formation(window_point(center,(i%20-10)*16000,(i//20-8)*16000,sampler.sites.radius))
    assert independent.formation(center)==original
    assert len(independent.cache)<=256 and len(independent.sites.cache)<=4096


def test_adjacent_physical_windows_share_formations_and_opportunities(reference):
    sampler,center,first=reference
    second,_=window_formations(sampler,window_point(center,32000,0,sampler.sites.radius))
    shared=set(first)&set(second)
    assert shared
    for identifier in shared:
        assert first[identifier]==second[identifier]
        assert select_sources(first[identifier],sampler.signature)==select_sources(second[identifier],sampler.signature)


def test_J1_contact_fragments_do_not_steal_a_neighboring_province(reference):
    sampler,_,_=reference
    from app.game.world.genesis.hydro_geometry.spatial import between
    a,b=[SurfacePoint(*u["center"]) for u in sampler.macro.units[:2]]
    parent=sampler.macro.unit_at(a)["geological_unit_id"]
    for _ in range(32):
        mid=between(a,b,1,2)
        if sampler.macro.unit_at(mid)["geological_unit_id"]==parent:
            a=mid
        else:
            b=mid
    left,right=sampler.formation(a),sampler.formation(b)
    assert left["physical_address"]==right["physical_address"]
    assert left["parent_unit_id"]!=right["parent_unit_id"]
    assert left["formation_id"]!=right["formation_id"]
    pending=left if left["contact_fragment_pending"] else right
    assert pending["contact_fragment_pending"]
    assert opportunities(pending,sampler.signature)["opportunities"]==[]


def test_no_adapter_fallback_or_legendary_and_no_hydrological_inference(reference):
    sampler,_,forms=reference
    catalog=load_catalog()
    for f in forms.values():
        adapted=adapt_formation(f,sampler.signature)
        assert adapted["canonical_authorizations"]==adapted["event_instance_ids"]==[]
        result=opportunities(f,sampler.signature,catalog)
        for model in ("aluvião","biomineral","glacial","litoral","recifal","meteoritico","veio_arcano","veio_anomalo"):
            assert not result["bridges"][model]["eligible"]
        assert all(s["rarity"]!="lendario" for s in select_sources(f,sampler.signature,catalog=catalog))
    f=deepcopy(next(iter(forms.values())))
    f["evidence_records"]["invented"]={"authority":"JR1","history_kind":"nonexistent"}
    with pytest.raises(ValueError,match="history"):
        adapt_formation(f,sampler.signature)


def test_routes_do_not_duplicate_opportunities_and_depth_restrictions(reference):
    sampler,_,forms=reference;catalog=load_catalog()
    duplicate_route_seen=False
    for f in forms.values():
        opp=opportunities(f,sampler.signature,catalog)["opportunities"]
        assert len({o["material_id"] for o in opp})==len(opp)
        duplicate_route_seen |= any(len(o["routes"])>1 for o in opp)
        for o in opp:
            low,high=catalog["materials"][o["material_id"]]["ocorrencia_geologica_v4"]["geometria_e_disponibilidade"]["indice_profundidade_referencia_intervalo_0_100"]
            assert low<=f["depth_index_0_100"]<=high
    assert duplicate_route_seen


def test_length_scaled_policy_zero_rate_and_pinned_geography(reference):
    sampler,_,forms=reference;catalog=load_catalog()
    counts=[]
    for factor in (0,500000,1000000,2000000):
        selected=[d for f in forms.values() for d in select_sources(f,sampler.signature,RegionalPolicy(rate_factor_ppm=factor),catalog)]
        counts.append(len(selected))
    assert counts==[0,33,71,131]
    f=next(f for f in forms.values() if select_sources(f,sampler.signature,catalog=catalog))
    assert select_sources(f,sampler.signature)==select_sources(deepcopy(f),sampler.signature)


def test_predefined_empty_window_is_retained():
    sampler=inputs(2026,63710000)
    center=land_windows(sampler)[2]
    forms,_=window_formations(sampler,center)
    assert forms
    assert all(not opportunities(f,sampler.signature)["opportunities"] for f in forms.values())


def test_cross_process_determinism(reference):
    sampler,center,_=reference
    expected=checksum(sampler.formation(center))
    code=f"from scripts.validate_regional_geology import inputs,land_windows; from app.game.world.genesis.terrain.field import checksum; s=inputs(42,63710000); print(checksum(s.formation(land_windows(s)[0])))"
    result=subprocess.run([sys.executable,"-c",code],cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,check=True)
    assert result.stdout.strip()==expected


@pytest.mark.parametrize("kwargs",[{"regional_version":True},{"regional_version":2},{"formation_spacing_m":1}])
def test_strict_version_and_resolution(kwargs):
    with pytest.raises(ValueError):
        RegionalConfig(**kwargs)
