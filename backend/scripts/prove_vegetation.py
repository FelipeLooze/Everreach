"""Actual SQLite community/collection proof. Never connects to everreach.db."""
import argparse,json,time
from pathlib import Path
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.character import Character
from app.db.models.region import Region
from app.db.models.location import Location
from app.db.models.world_spatial import LocationSpatialAnchor
from app.db.models.skill import Skill,CharacterSkill
from app.db.models.item import ItemInstance
from app.core.enums import ItemType,ItemInstanceMode,ItemLocationType,ItemOwnerType,ToolCapability
from app.game.items.service import create_item_definition,create_item_instance,move_item_instance,set_item_owner
from app.game.items.tools import configure_item_tool_profile
from app.game.world.genesis.environment.service import initialize_environment
from app.game.world.genesis.environment.config import EnvironmentConfigC3
from app.game.world.genesis.vegetation import service as vg
from app.game.world.genesis.vegetation.config import VegetationConfig
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.time.clock import get_world_time
from scripts.validate_water_c3 import import_disposable
from scripts.validate_vegetation import inputs_vg1,ROOT,OUT,centers


def prepare(db,sampler):
    seed=sampler.environment.regional.terrain.plan.source.seed
    evidence=json.loads((ROOT/f'artifacts/water-c3-compatibility/seed-{seed}/C3-hr1-evidence.json').read_text())
    cid,_=import_disposable(db,sampler.environment,sampler.water,evidence)
    initialize_environment(db,cid,EnvironmentConfigC3())
    vg.initialize_vegetation(db,cid,sampler.config,experimental=True)
    return cid


def find_collectable(sampler):
    snapshots=ROOT/"artifacts/vegetation-vg1/seed-42"/sampler.config.policy/"communities.json"
    if snapshots.exists():
        points=[SurfacePoint(*s["point"]) for s in json.loads(snapshots.read_text(encoding="utf-8")).values() if s["established"]]
    else:points=list(centers(42).values())
    for point in points:
        community=sampler.sample(point)
        for p in community["populations"]:
            sp=sampler.catalog.species[p["species_id"]]
            if sp.stock and any(part["parte"] in ("folhas","ramos","fibras","frondes","tufo","fragmentos") and part["quantidade_max"] for part in sp.parts()):
                return point,sp.id
    raise ValueError("No real collectible population in measured samples")


def actor_at(db,cid,individual,sampler,*,tool_key="vg1_experimental_field_tool"):
    region=Region(campaign_id=cid,name="Vg1 isolated technical proof")
    db.add(region);db.flush()
    location=Location(region_id=region.id,name="Technical vegetation plot",type="natural")
    db.add(location);db.flush()
    db.add(LocationSpatialAnchor(location_id=location.id,campaign_id=cid,point=individual.baseline["point"]))
    actor=Character(campaign_id=cid,name="Vg1 test operator",region_id=region.id,location_id=location.id)
    db.add(actor);db.flush()
    definition=create_item_definition(db,key=tool_key,name="Vg1 certified test field tool",item_type=ItemType.TOOL,instance_mode=ItemInstanceMode.UNIQUE)
    configure_item_tool_profile(db,definition,capabilities={ToolCapability.CUTTING,ToolCapability.SAWING})
    tool=create_item_instance(db,definition)
    move_item_instance(db,tool,location_type=ItemLocationType.CHARACTER,location_ref=actor.id)
    set_item_owner(db,tool,owner_type=ItemOwnerType.CHARACTER,owner_ref=actor.id)
    sp=sampler.catalog.species[individual.baseline["species_id"]]
    parts=sp.parts();capabilities=set(c for p in parts for c in p["protocolo_campo_v7"]["capacidades_necessarias_da_ferramenta"])
    vg.certify_botanical_tool(db,definition.id,capabilities,experimental=True)
    profs={next(v for k,v in p["protocolo_campo_v7"].items() if k.startswith("profici") and k.endswith("principal_id")) for p in parts}
    profs.add("EV-PROF-BOT-001")
    for prof in profs:
        if db.get(Skill,prof) is None:db.add(Skill(id=prof,name="Vg1 explicit test training "+prof,category="botanical_test"));db.flush()
        db.add(CharacterSkill(character_id=actor.id,skill_id=prof,mastery=80))
    db.flush()
    return actor,tool


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--database",default="persistent-proof.sqlite")
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    sampler=inputs_vg1(42,"exploration_mosaic_v1");point,sid=find_collectable(sampler)
    path=(OUT/args.database).resolve()
    if path.parent!=OUT.resolve():raise ValueError("Proof database must stay in the isolated artifact directory")
    if path.exists():raise ValueError("Proof DB already exists; inspect it or choose another output instead of overwriting")
    engine=create_engine("sqlite:///"+str(path));event.listen(engine,"connect",enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        started=time.perf_counter();cid=prepare(db,sampler);preparation=time.perf_counter()-started
        started=time.perf_counter();ind=vg.materialize_individual(db,cid,point,sid,0);materialization=time.perf_counter()-started
        actor,tool=actor_at(db,cid,ind,sampler)
        sp=sampler.catalog.species[sid]
        part=next(p for p in sp.parts() if ind.state["part_stock"].get(p["id"],0)>0)
        # Set a legal catalog window on the disposable world's existing clock.
        season=part["disponibilidade"]["estacoes"][0]
        clock=get_world_time(db,cid);clock.month={"primavera":3,"verao":6,"outono":9,"inverno":12}[season]
        clock.hour={"manha":8,"tarde":14,"noite":22}[part["disponibilidade"]["periodos_do_dia"][0]]
        before=json.loads(json.dumps(ind.state));iid=ind.individual_id;actorid=actor.id
        started=time.perf_counter();receipt=vg.harvest(db,cid,actor.id,iid,part["id"],1,tool.id,"proof-harvest-1");collection_time=time.perf_counter()-started
        replay=vg.harvest(db,cid,actor.id,iid,part["id"],1,tool.id,"proof-harvest-1")
        removal=(vg.remove_individual(db,cid,actor.id,iid,tool.id,"proof-removal-1") if ind.state["alive"] else
            {"removed_by_finite_destructive_harvest":True,"individual_alive":False})
        db.commit()
    with Session(engine) as db:
        started=time.perf_counter();revisited=vg.materialize_individual(db,cid,point,sid,0);revisit_time=time.perf_counter()-started
        community=vg.query_community(db,cid,point)
        lots=db.query(ItemInstance).filter_by(definition_id=part["item_id"],location_ref=actorid).all()
        report={"campaign_id":cid,"database":str(path.relative_to(ROOT)),"individual_id":iid,"species_id":sid,
            "point":list(point.xyz),"before":before,"harvest":receipt,"idempotent_replay":receipt==replay,
            "removal":removal,"revisited":revisited.state,"inventory_quantity":sum(x.quantity for x in lots),
            "community_removed_individuals":community["removed_individuals"],"real_campaigns_touched":False,
            "timing_seconds":{"prepare_sources":preparation,"materialize_community_and_individual":materialization,
                "harvest":collection_time,"revisit":revisit_time},
            "test_operator_training_and_tool_certification":"explicit_disposable_only_no_automatic_profession_import"}
        assert not revisited.state["alive"] and report["inventory_quantity"]==1 and report["idempotent_replay"]
        (OUT/"persistent-proof.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False),flush=True)
    engine.dispose()


if __name__=="__main__":main()
