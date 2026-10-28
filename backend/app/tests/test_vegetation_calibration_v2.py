from copy import deepcopy
from dataclasses import replace
import json,os,subprocess,sys
from pathlib import Path
import pytest
from app.game.world.genesis.vegetation.config import (VegetationConfigV2,PartCalibrationV1,parse_vegetation_config,make_vegetation_sampler)
from app.game.world.genesis.vegetation.v2 import VegetationSamplerV2
from app.game.world.genesis.vegetation.field import VegetationSampler,eligibility
from app.game.world.genesis.vegetation.diagnostics import route_diagnostics,visual_change
from app.game.world.genesis.vegetation.evidence_audit import extreme_evidence
from app.game.world.genesis.vegetation import service as service
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.terrain.address import point_on_face
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.geology.regional.experiment import window_point
from app.db.models.item import ItemDefinition,ItemInstance
from app.game.time.clock import get_world_time
from scripts.validate_vegetation import inputs_vg1,centers,ROOT
from scripts.prove_vegetation import prepare,actor_at


@pytest.fixture(scope="module")
def sources():return inputs_vg1(42,"exploration_mosaic_v1")


@pytest.fixture(scope="module")
def v2(sources):return VegetationSamplerV2(sources.environment,sources.water)


def test_explicit_dispatch_and_json_roundtrip_preserve_v1(sources,v2):
    cfg=parse_vegetation_config(json.loads(json.dumps(v2.config.model_dump(mode="json"))))
    assert cfg==v2.config and isinstance(make_vegetation_sampler(sources.environment,sources.water,cfg),VegetationSamplerV2)
    with pytest.raises(ValueError,match="factory"):VegetationSampler(sources.environment,sources.water,cfg)
    assert sources.signature!=v2.signature
    assert sources.environment.signature==v2.environment.signature and sources.water.signature==v2.water.signature
    root=ROOT/"artifacts/vegetation-vg1/seed-42/exploration_mosaic_v1/windows.json"
    for w in json.loads(root.read_text(encoding="utf-8")).values():
        s=w["grid"][0][0]
        assert sources.sample(SurfacePoint(*s["point"]))==s


@pytest.mark.parametrize("region",["wet","moderate","arid","cold","dry"])
def test_coverage_not_thinned_for_diversity_and_locally_eligible(v2,region):
    point=centers(42)[region];s=v2.sample(point)
    assert s["ecological_base_cover_ppm"]<=s["cover_ppm"]<=s["ecological_cover_ceiling_ppm"]
    assert s["cover_ppm"]==sum(p["cover_ppm"] for p in s["populations"])
    e=v2.environment.sample(SurfacePoint(*s["point"]));w=v2.water_facts(SurfacePoint(*s["point"]))
    for p in s["populations"]:assert eligibility(v2.catalog.species[p["species_id"]],e,w)[0]=="eligible"
    if region in ("cold","dry"):assert not s["established"]


def test_regional_continuity_distinguishes_identity_and_structure(sources,v2):
    center=centers(42)["moderate"]
    points=[window_point(center,250*(i-10),0,v2.radius) for i in range(21)]
    a=route_diagnostics([sources.sample(p) for p in points],5000)
    b=route_diagnostics([v2.sample(p) for p in points],5000)
    assert b["dominant_changes"]<a["dominant_changes"] and b["form_changes"]==0
    assert len({v2.sample(p)["strata_cover_ppm"]["canopy"] for p in points})>1
    s=v2.sample(center);clone=deepcopy(s);clone["dominant_species"]="different_id_same_architecture"
    assert not visual_change(s,clone)


def test_order_face_aliases_bounded_caches_and_polar_addresses(v2):
    points=list(centers(42).values());a=[v2.sample(p) for p in points];v2.cache.clear();v2.cohorts.clear()
    assert a==list(reversed([v2.sample(p) for p in reversed(points)]))
    p=point_on_face(0,100,51,100);q=point_on_face(2,0,51,100)
    assert p==q and v2.sample(p)==v2.sample(q)
    for p in (SurfacePoint(0,0,1),SurfacePoint(0,0,-1)):assert v2.sample(p)["community_id"].startswith("vg2:")
    assert len(v2.cache)<=128 and len(v2.cohorts)<=256
    weights=list(v2._anchors(SurfacePoint(100000000,99999999,2000000)))
    assert abs(sum(w for _,w in weights)-1000000)<20


def test_interprocess_determinism(v2):
    code="from scripts.validate_vegetation import inputs_vg1,centers;from app.game.world.genesis.vegetation.v2 import VegetationSamplerV2;from app.game.world.genesis.terrain.field import checksum;v=inputs_vg1(42);print(checksum(VegetationSamplerV2(v.environment,v.water).sample(centers(42)['wet'])))"
    output=subprocess.check_output([sys.executable,"-c",code],cwd=Path(__file__).resolve().parents[2],env=dict(os.environ,PYTHONHASHSEED="431"),text=True)
    assert output.strip()==checksum(v2.sample(centers(42)["wet"]))


def test_all_extremes_have_specific_audits_and_no_false_proof(v2):
    point=centers(42)["cold"];e=v2.environment.sample(point);w=v2.water_facts(point);audited=[]
    for s in v2.catalog.species.values():
        if s.extreme_json:
            a=extreme_evidence(s,e,w);audited.append(a)
            assert a["missing"] and not a["materialization_authorized"]
            assert a["source_checksums"]["water"]==v2.water.signature
            if s.magic=="excepcional":assert any(str(s.anomaly) in m for m in a["missing"])
    assert len(audited)==96 and len({a["habitat_id"] for a in audited})==16


def choose_part(v2):
    for point in centers(42).values():
        for pop in v2.sample(point)["populations"]:
            s=v2.catalog.species[pop["species_id"]]
            for part in s.parts():
                if part["parte"] in ("folhas","ramos","fibras","tufo","fragmentos","frondes"):
                    return point,s,part
    raise AssertionError("No real founder part")


def calibration(s,part,**overrides):
    values=dict(species_id=s.id,part_id=part["id"],organism_type=s.kind,max_mature_units=1,unit_mass_mg=5000,
        inventory_mg_per_weight_unit=1000000,
        tissue_pool_id="test-only-leaf-pool",available_tissue_mass_mg=20000,removable_fraction_ppm=500000,
        evidence_ref="synthetic_test_fixture_not_a_real_world_measurement",method="explicit synthetic tissue budget for transaction tests only",status="reviewed_experimental")
    return PartCalibrationV1(**{**values,**overrides})


@pytest.mark.parametrize("change",[{"unit_mass_mg":0},{"unit_mass_mg":None},{"max_mature_units":100},{"removable_fraction_ppm":-1},{"status":"proposed"}])
def test_unreviewed_zero_mass_or_unbounded_yield_rejected(v2,change):
    _,s,p=choose_part(v2)
    with pytest.raises(ValueError):calibration(s,p,**change)


def test_stockless_default_does_not_invent_resources(db_session,v2):
    point,s,p=choose_part(v2);cid=prepare(db_session,v2)
    ind=service.materialize_individual(db_session,cid,point,s.id,0)
    assert not any(ind.state["part_stock"].values()) and ind.baseline["stock_calibration"]=="pending_reviewed_mass_and_yield"


def prepared_collection(db,v2):
    point,s,p=choose_part(v2);c=calibration(s,p)
    sampler=VegetationSamplerV2(v2.environment,v2.water,VegetationConfigV2(resource_calibrations=(c,)))
    cid=prepare(db,sampler);ind=service.materialize_individual(db,cid,point,s.id,0)
    actor,tool=actor_at(db,cid,ind,sampler);clock=get_world_time(db,cid)
    clock.month={"primavera":3,"verao":6,"outono":9,"inverno":12}[p["disponibilidade"]["estacoes"][0]]
    clock.hour={"manha":8,"tarde":14,"noite":22}[p["disponibilidade"]["periodos_do_dia"][0]]
    db.flush();return sampler,cid,point,s,p,ind,actor,tool


def test_reviewed_finite_mass_harvest_survives_cache_clear_and_revisit(db_session,v2):
    db=db_session;v,cid,point,s,p,ind,actor,tool=prepared_collection(db,v2)
    r=service.harvest(db,cid,actor.id,ind.individual_id,p["id"],1,tool.id,"v2-collect")
    assert r["unit_mass_mg"]==5000 and db.get(ItemDefinition,p["item_id"]).base_weight==0.005
    from app.game.items.containers import get_item_total_weight
    assert get_item_total_weight(db,db.get(ItemInstance,r["item_instance_id"]))==0.005
    assert service.harvest(db,cid,actor.id,ind.individual_id,p["id"],1,tool.id,"v2-collect")==r
    db.commit();service._cache.clear();db.expire_all()
    revisit=service.materialize_individual(db,cid,point,s.id,0)
    assert revisit.state["part_stock"][p["id"]]==0
    assert service.context(db,cid).config==v.config
    assert db.query(ItemInstance).filter_by(definition_id=p["item_id"]).one().quantity==1
    with pytest.raises(ValueError):service.harvest(db,cid,actor.id,ind.individual_id,p["id"],1,tool.id,"v2-second")


def test_existing_legacy_zero_mass_item_is_not_silently_changed(db_session,v2):
    db=db_session;v,cid,point,s,p,ind,actor,tool=prepared_collection(db,v2)
    item=ItemDefinition(id=p["item_id"],key=p["item_id"].lower().replace("-","_"),name=p["item_nome"],type="MISC",instance_mode="STACKABLE",base_weight=0)
    db.add(item);db.flush();before=deepcopy(ind.state)
    with pytest.raises(ValueError,match="explicit migration"):service.harvest(db,cid,actor.id,ind.individual_id,p["id"],1,tool.id,"collision")
    assert db.get(ItemDefinition,p["item_id"]).base_weight==0 and ind.state==before


def test_shared_tissue_cannot_be_double_allocated(v2):
    _,s,p=choose_part(v2);other=next(x for x in s.parts() if x["id"]!=p["id"])
    a=calibration(s,p,available_tissue_mass_mg=10000,removable_fraction_ppm=500000)
    b=calibration(s,other,available_tissue_mass_mg=10000,removable_fraction_ppm=500000)
    with pytest.raises(ValueError,match="double allocate"):
        VegetationSamplerV2(v2.environment,v2.water,VegetationConfigV2(resource_calibrations=(a,b)))
