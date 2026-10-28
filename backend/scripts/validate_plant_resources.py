"""R1 coverage and real v22 founders, all five reference seeds; isolated SQLite only."""
import argparse,csv,gc,json,time
from collections import Counter
from pathlib import Path
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.character import CharacterAttribute
from app.db.models.world_spatial import LocationSpatialAnchor
from app.db.models.item import ItemInstance
from app.core.enums import CharacterAttributeKey
from app.game.attributes.service import ensure_attribute_catalog
from app.game.time.clock import get_world_time,advance_world_time
from app.game.items.containers import get_item_unit_weight
from app.game.world.genesis.vegetation import service
from app.game.world.genesis.vegetation.resources import initialize_resources,derive,TYPE_HEIGHT_CM,load_flora_catalog,ResourceConfigR1
from app.game.world.genesis.vegetation.actions import resolve_plant_action
from app.game.world.genesis.vegetation.config import make_vegetation_sampler,VegetationConfigV2
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.schemas.action import PlantActionRequest
from scripts.validate_vegetation import inputs_vg1,ROOT
from scripts.prove_vegetation import prepare,actor_at

OUT=ROOT/"artifacts/plant-resources-r1"
KINDS=("flor","erva","arbusto","arvore","graminea","liquen")


def coverage():
    start=time.perf_counter();cat=load_flora_catalog();records=[];masses=[];yields=[];types=Counter();states=Counter();pending=Counter()
    for s in cat.species.values():
        h=s.height_cm or TYPE_HEIGHT_CM[s.kind];profile=derive(s,(h[0]+h[1])//2)
        for pid,p in profile["parts"].items():
            records.append({"species_id":s.id,"kind":s.kind,**p,"height_reference_source":"catalog_midpoint" if s.height_cm else "versioned_type_architecture"})
            masses.append(p["unit_mass_mg"]);yields.append(p["max_units"]);types[s.kind]+=1;states[p["state"]]+=1
            if p["reason"]:pending[p["reason"]]+=1
    report={"species":len(cat.species),"parts":len(records),"positive_mass_profiles":len(masses),"usable_raw_parts":states["usable"],
        "pending_parts":states["pending"],"pending_reasons":dict(pending),"species_with_usable_raw_profile":len({p["species_id"] for p in records if p["state"]=="usable"}),
        "unit_mass_mg_range":[min(masses),max(masses)],"stock_range":[min(yields),max(yields)],"unique_unit_masses":len(set(masses)),
        "unique_stocks":len(set(yields)),"part_types":dict(types),"calibration_seconds":time.perf_counter()-start,
        "ecological_availability_not_implied":True,"actual_collected_species_reported_separately":True,"parameters":ResourceConfigR1().model_dump()}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"coverage.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (OUT/"part-calibrations.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"part-calibrations.csv").open("w",newline="",encoding="utf-8-sig") as f:
        fields=("species_id","kind","part_id","item_id","part","unit_mass_mg","max_units","per_action_max","state","reason","pool")
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(records)
    return report


def inputs(seed):
    old=inputs_vg1(seed);return make_vegetation_sampler(old.environment,old.water,VegetationConfigV2())


def candidates(seed,kind):
    snapshots=json.loads((ROOT/f"artifacts/vegetation-1.0.1/seed-{seed}/communities.json").read_text(encoding="utf-8"))
    seen=set()
    for b in snapshots.values():
        for p in b["populations"]:
            if p["kind"]==kind and p["species_id"] not in seen:
                seen.add(p["species_id"]);yield SurfacePoint(*b["point"]),p["species_id"]


def actual_individual(db,cid,sampler,seed,kind):
    for point,sid in candidates(seed,kind):
        if sid not in {p["species_id"] for p in sampler.sample(point)["populations"]}:raise ValueError("Vg2 geography changed")
        for slot in range(8):
            try:ind=service.materialize_individual(db,cid,point,sid,slot)
            except ValueError as exc:
                if "microsite unsupported" in str(exc):continue
                raise
            for p in sampler.catalog.species[sid].parts():
                if ind.state["part_stock"][p["id"]]>0:return point,ind,p
    raise ValueError("No real founder with a mature raw part for "+kind)


def prepare_operator(db,cid,ind,sampler):
    actor,tool=actor_at(db,cid,ind,sampler,tool_key="r1_field_kit_"+ind.baseline["species_id"].lower().replace("-","_"));ensure_attribute_catalog(db)
    for key in CharacterAttributeKey:
        db.add(CharacterAttribute(character_id=actor.id,key=key.value,value=10))
    from app.game.items.equipment import configure_item_equipment_profile,equip_item
    from app.core.enums import EquipmentSlot
    configure_item_equipment_profile(db,tool.definition,allowed_slots={EquipmentSlot.MAIN_HAND})
    equip_item(db,tool,slot=EquipmentSlot.MAIN_HAND)
    db.flush();return actor,tool


def set_window(db,cid,part,ind=None,sampler=None):
    c=get_world_time(db,cid)
    name=part["disponibilidade"]["estacoes"][0]
    if name=="todo_ano_condicionado_a_atividade_biologica":
        c.month=6
        if ind is not None and sampler is not None:
            e=sampler.environment.sample(SurfacePoint(*ind.baseline["point"]));w=sampler.water_facts(SurfacePoint(*ind.baseline["point"]))
            indices=[i for i in range(4) if e["physical_inputs"]["C3_seasons"][i]["temperature_centi_c"]>0 and sampler.water.solution.periods[i]["fluxes"]["evapotranspiration"][w["node"]]>0]
            if not indices:raise ValueError("No actual modeled seasonal activity window")
            c.month=(3,6,9,12)[indices[0]]
    else:c.month={"primavera":3,"verao":6,"outono":9,"inverno":12}[name]
    c.hour={"manha":8,"tarde":14,"noite":22,"madrugada":2,"crepusculo":18}[part["disponibilidade"]["periodos_do_dia"][0]]
    db.flush()


def run(seed,path):
    if path.exists():raise ValueError("Refusing to overwrite an existing proof database")
    start=time.perf_counter();sampler=inputs(seed)
    engine=create_engine("sqlite:///"+str(path));event.listen(engine,"connect",enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    records=[]
    with Session(engine) as db:
        cid=prepare(db,sampler);initialize_resources(db,cid,experimental=True)
        for kind in KINDS:
            point,ind,part=actual_individual(db,cid,sampler,seed,kind)
            actor,tool=prepare_operator(db,cid,ind,sampler);set_window(db,cid,part,ind,sampler)
            observation=resolve_plant_action(db,cid,actor.id,PlantActionRequest(kind="observe",individual_id=ind.individual_id),"observe-"+kind).plant_result
            initial=json.loads(json.dumps(ind.state));key="collect-"+kind
            request=PlantActionRequest(kind="harvest",individual_id=ind.individual_id,part_id=part["id"],quantity=1,tool_instance_id=tool.id)
            receipt=resolve_plant_action(db,cid,actor.id,request,key).plant_result
            minute=get_world_time(db,cid).total_minutes();replay=resolve_plant_action(db,cid,actor.id,request,key).plant_result
            assert receipt["item_instance_id"]==replay["item_instance_id"] and get_world_time(db,cid).total_minutes()==minute
            before=json.loads(json.dumps(ind.state))
            try:service.harvest(db,cid,actor.id,ind.individual_id,part["id"],100000,tool.id,"excess-"+kind)
            except ValueError:pass
            else:raise AssertionError("Over-collection accepted")
            assert ind.state==before
            records.append({"seed":seed,"kind":kind,"species_id":ind.baseline["species_id"],"species_name":sampler.catalog.species[ind.baseline["species_id"]].name,
                "point":list(point.xyz),"individual_id":ind.individual_id,"part":part["parte"],"part_id":part["id"],
                "initial":initial,"observation":observation,"receipt":receipt,"after":before,"actor_id":actor.id,"tool_id":tool.id,
                "idempotent_replay":True,"over_collection_refused":True})
        # Cutting a real founder tree removes its stock and yields no invented timber.
        tree=next(r for r in records if r["kind"]=="arvore");point=SurfacePoint(*tree["point"])
        extra=service.materialize_individual(db,cid,point,tree["species_id"],tree["initial"].get("slot",1))
        actor,tool=prepare_operator(db,cid,extra,sampler)
        removal=resolve_plant_action(db,cid,actor.id,PlantActionRequest(kind="remove",individual_id=extra.individual_id,tool_instance_id=tool.id),"remove-tree").plant_result
        extra_id=extra.individual_id;db.commit()
    with Session(engine) as db:
        for r in records:
            ind=service.materialize_individual(db,cid,SurfacePoint(*r["point"]),r["species_id"],db.get(models.GenesisPlantIndividual,(cid,r["individual_id"])).baseline["slot"])
            assert ind.state==r["after"]
            lot=db.get(ItemInstance,r["receipt"]["item_instance_id"])
            assert lot.quantity==1 and get_item_unit_weight(db,lot)>0
            r["reopened_state"]=ind.state;r["inventory_weight"]=get_item_unit_weight(db,lot)*lot.quantity
        assert not db.get(models.GenesisPlantIndividual,(cid,extra_id)).state["alive"]
    engine.dispose()
    report={"seed":seed,"campaign_id":cid,"real_v22_collections":len(records),"records":records,"tree_removal":removal,
        "database":str(path.relative_to(ROOT)),"elapsed_seconds":time.perf_counter()-start,"real_campaigns_modified":False}
    (OUT/f"seed-{seed}-proof.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"seed":seed,"collections":len(records),"elapsed_seconds":report["elapsed_seconds"]}),flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--seeds",type=int,nargs="+",default=[42,0,7,2026,12345]);parser.add_argument("--coverage-only",action="store_true");args=parser.parse_args()
    print(json.dumps(coverage()),flush=True)
    if not args.coverage_only:
        for seed in args.seeds:run(seed,OUT/f"seed-{seed}-proof.sqlite");gc.collect()
