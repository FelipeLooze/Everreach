from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json,os,subprocess,sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.item import ItemDefinition,ItemInstance
from app.db.models.world_plant_resources import GenesisPlantResources
from app.db.models.world_vegetation import GenesisPlantIndividual,GenesisPlantAction
from app.game.world.genesis.vegetation.resources import *
from app.game.world.genesis.vegetation import service
from app.game.world.genesis.vegetation.actions import resolve_plant_action,inspect
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.terrain.field import checksum
from app.game.items.containers import get_item_total_weight,get_item_unit_weight
from app.game.time.clock import get_world_time,advance_world_time
from app.schemas.action import PlantActionRequest
from scripts.validate_plant_resources import inputs,actual_individual,prepare_operator,set_window,candidates
from scripts.prove_vegetation import prepare


@pytest.fixture(scope="module")
def sampler():return inputs(42)


def setup(db,v,kind="flor"):
    cid=prepare(db,v);initialize_resources(db,cid,experimental=True)
    point,ind,part=actual_individual(db,cid,v,42,kind)
    actor,tool=prepare_operator(db,cid,ind,v);set_window(db,cid,part,ind,v)
    return cid,point,ind,part,actor,tool


def request(ind,part,tool,quantity=1):
    return PlantActionRequest(kind="harvest",individual_id=ind.individual_id,part_id=part["id"],quantity=quantity,tool_instance_id=tool.id)


def test_catalog_coverage_and_physical_pool_bounds():
    cat=load_flora_catalog();counts=Counter();masses=set();stocks=set()
    for s in cat.species.values():
        heights=s.height_cm or TYPE_HEIGHT_CM[s.kind];p=derive(s,sum(heights)//2)
        for part in p["parts"].values():
            assert part["unit_mass_mg"]>0 and part["max_units"]>0
            if part["part"] in ("frutos","sementes","esporos","propagulos","corpo_frutifero"):
                assert part["maturity_required"]=="fruiting"
            counts[part["state"]]+=1;masses.add(part["unit_mass_mg"]);stocks.add(part["max_units"])
        for pool,budget in p["pools_mg"].items():
            assert sum(r["unit_mass_mg"]*r["max_units"] for r in p["parts"].values() if r["pool"]==pool)<=budget
    assert counts=={"usable":6045,"pending":147} and len(masses)>2000 and len(stocks)>40


def test_mass_and_yield_are_independent_of_rarity():
    s=load_flora_catalog().species["EV-FL-0043"]
    a=derive(replace(s,rarity=0),100);b=derive(replace(s,rarity=100),100)
    assert a["parts"]==b["parts"] and a["pools_mg"]==b["pools_mg"]
    assert a["future_recovery"]["active"] is False


def test_sparse_overrides_are_bounded_and_versioned():
    s=load_flora_catalog().species["EV-FL-0001"];pid=s.parts()[0]["id"]
    c=ResourceConfigR1(overrides={pid:PartOverride(unit_mass_mg=20,max_units=2,rationale="game balance exception")})
    assert derive(s,40,c)["parts"][pid]["unit_mass_mg"]==20
    with pytest.raises(ValueError):derive(s,40,ResourceConfigR1(overrides={pid:PartOverride(unit_mass_mg=10**9,max_units=999,rationale="invalid huge biomass")}))
    with pytest.raises(ValueError):ResourceConfigR1(resource_version=True)
    with pytest.raises(ValueError):PartOverride(unit_mass_mg=0,rationale="zero mass is invalid")


@pytest.mark.parametrize("seed",[42,0,7,2026,12345])
def test_five_seed_real_founder_derivations_are_deterministic(seed):
    v=inputs(seed);point,sid=next(candidates(seed,"erva"));before=checksum(v.descriptor),checksum(v.water.to_dict())
    p=v.sample(point);sp=v.catalog.species[sid];pop=next(p for p in p["populations"] if p["species_id"]==sid)
    a=derive(sp,pop["height_cm"]);b=derive(sp,pop["height_cm"])
    assert a==b and all(r["unit_mass_mg"]>0 for r in a["parts"].values())
    assert before==(checksum(v.descriptor),checksum(v.water.to_dict()))


@pytest.mark.parametrize("kind",["flor","erva","arbusto","arvore","graminea","liquen"])
def test_real_v22_parts_enter_inventory_and_do_not_regrow(db_session,sampler,kind):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler,kind);before=deepcopy(ind.state)
    r=resolve_plant_action(db,cid,actor.id,request(ind,p,tool),"collect-real").plant_result
    assert r["exported_mass_mg"]>0 and r["unit_mass_mg"]>0 and r["quantity"]==1
    lot=db.get(ItemInstance,r["item_instance_id"])
    assert lot.definition_id==p["item_id"] and get_item_total_weight(db,lot)==r["exported_mass_mg"]/1000000
    assert ind.state["part_stock"][p["id"]]<before["part_stock"][p["id"]]
    state=deepcopy(ind.state);minute=get_world_time(db,cid).total_minutes()
    replay=resolve_plant_action(db,cid,actor.id,request(ind,p,tool),"collect-real").plant_result
    assert replay["item_instance_id"]==r["item_instance_id"] and get_world_time(db,cid).total_minutes()==minute
    advance_world_time(db,cid,120*24*60)
    again=service.materialize_individual(db,cid,point,ind.baseline["species_id"],ind.baseline["slot"])
    assert again.state==state
    assert db.query(ItemInstance).filter_by(definition_id=p["item_id"]).count()==1


def test_legacy_zero_definition_and_old_instance_stay_zero(db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler)
    definition=ItemDefinition(id=p["item_id"],key=p["item_id"].lower().replace("-","_"),name=p["item_nome"],type="MISC",instance_mode="STACKABLE",base_weight=0)
    db.add(definition);db.flush();old=ItemInstance(definition_id=definition.id,quantity=2);db.add(old);db.flush()
    r=service.harvest(db,cid,actor.id,ind.individual_id,p["id"],1,tool.id,"new-mass")
    assert definition.base_weight==0 and old.unit_weight_override is None and get_item_total_weight(db,old)==0
    new=db.get(ItemInstance,r["item_instance_id"]);assert get_item_unit_weight(db,new)>0 and new.definition_id==old.definition_id
    from app.game.inventory.service import add_item
    add_item(db,actor.id,p["item_nome"],1)
    assert new.quantity==1 and new.weight_authority


def test_invalid_collection_is_atomic_and_tissue_cannot_be_duplicated(db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler);before=deepcopy(ind.state)
    with pytest.raises(ValueError):service.harvest(db,cid,actor.id,ind.individual_id,p["id"],100000,tool.id,"too-many")
    with pytest.raises(ValueError):service.harvest(db,cid,actor.id,ind.individual_id,"EV-FL-9999-P01",1,tool.id,"wrong-part")
    assert ind.state==before and db.query(GenesisPlantAction).count()==0
    corrupt=deepcopy(ind.state);corrupt["tissue_remaining_mg"]["vegetative"]+=1
    with pytest.raises(ValueError,match="conservation"):validate_state(ind.baseline,corrupt)
    with pytest.raises(ValueError,match="reconfigure"):initialize_resources(db,cid,ResourceConfigR1(collect_minutes=4),experimental=True)


def test_late_activation_does_not_rewrite_existing_individuals(db_session,sampler):
    db=db_session;cid=prepare(db,sampler);point,sid=next(candidates(42,"arbusto"))
    ind=service.materialize_individual(db,cid,point,sid,0);baseline=deepcopy(ind.baseline);state=deepcopy(ind.state)
    initialize_resources(db,cid,experimental=True)
    again=service.materialize_individual(db,cid,point,sid,0)
    assert again.baseline==baseline and again.state==state and "resource_signature" not in baseline
    new=service.materialize_individual(db,cid,point,sid,1)
    assert "resource_signature" in new.baseline


def test_http_action_inventory_replay_and_undo(client,db_session,sampler,fake_llm):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler);db.commit();initial=deepcopy(ind.state)
    before_calls=len(fake_llm.calls)
    url=f"/api/campaigns/{cid}/actions";params={"character_id":actor.id}
    body={"text":"Coletar esta parte da planta", "action_key":"http-plant-1","plant_action":request(ind,p,tool).model_dump()}
    response=client.post(url,params=params,json=body)
    assert response.status_code==200,response.text
    r=response.json()["plant_result"];assert r["item_id"]==p["item_id"] and r["exported_mass_mg"]>0
    second=client.post(url,params=params,json=body);assert second.status_code==200,second.text
    assert second.json()["plant_result"]["item_instance_id"]==r["item_instance_id"]
    assert len(fake_llm.calls)==before_calls
    inventory=client.get(f"/api/campaigns/{cid}/inventory",params=params)
    assert inventory.status_code==200,inventory.text
    displayed=next(i for i in inventory.json()["items"] if i["item_instance_id"]==r["item_instance_id"])
    assert displayed["unit_weight"]==r["unit_mass_mg"]/1000000
    assert inventory.json()["total_weight"]>0
    assert db.query(ItemInstance).filter_by(definition_id=p["item_id"]).one().quantity==1
    undo=client.post(url+"/undo-last",params=params,json={"reason":"Corrigir minha escolha"})
    assert undo.status_code==200,undo.text
    db.expire_all();assert db.get(GenesisPlantIndividual,(cid,ind.individual_id)).state==initial
    assert db.query(ItemInstance).filter_by(definition_id=p["item_id"]).count()==0


def test_look_is_lazy_local_and_repeated_observation_does_not_restock(db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler)
    from app.game.world.genesis.vegetation.actions import encounter
    items=encounter(db,cid,actor);count=db.query(GenesisPlantIndividual).count()
    assert items and len(items)<=8 and all(i["distance_m"]<=5 for i in items)
    assert all("point" not in i for i in items)
    assert encounter(db,cid,actor)==items and db.query(GenesisPlantIndividual).count()==count


def test_outer_rollback_and_reset_include_resources(db_session,sampler):
    db=db_session;cid=prepare(db,sampler);db.commit();initialize_resources(db,cid,experimental=True);db.rollback()
    assert db.get(GenesisPlantResources,cid) is None
    initialize_resources(db,cid,experimental=True)
    from app.game.world.reset import delete_campaign
    assert delete_campaign(db,cid);db.flush();assert db.get(GenesisPlantResources,cid) is None


def test_resource_calibration_between_processes():
    code="from app.game.world.genesis.vegetation.resources import *;print(checksum(derive(load_flora_catalog().species['EV-FL-1501'],1800)))"
    expected=checksum(derive(load_flora_catalog().species["EV-FL-1501"],1800))
    result=subprocess.check_output([sys.executable,"-c",code],cwd=Path(__file__).resolve().parents[2],env=dict(os.environ,PYTHONHASHSEED="245"),text=True)
    assert result.strip()==expected


def test_weight_affects_capacity_and_container_limits(db_session,sampler):
    from app.game.inventory.service import add_item
    from app.game.items.encumbrance import get_character_encumbrance
    from app.game.items.service import create_item_definition,create_item_instance,move_item_instance,set_item_owner
    from app.game.items.containers import configure_item_container_profile,store_item_in_container,ContainerError
    from app.core.enums import ItemType,ItemInstanceMode,ItemLocationType,ItemOwnerType
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler)
    receipt=service.harvest(db,cid,actor.id,ind.individual_id,p["id"],1,tool.id,"weight-proof")
    lot=db.get(ItemInstance,receipt["item_instance_id"]);mass=get_item_total_weight(db,lot)
    add_item(db,actor.id,"R1 capacity control",base_weight=25-mass/2)
    assert get_character_encumbrance(db,actor.id).load_ratio>1
    definition=create_item_definition(db,key="r1_small_container",name="R1 small vessel",item_type=ItemType.CONTAINER,instance_mode=ItemInstanceMode.UNIQUE)
    configure_item_container_profile(db,definition,weight_capacity=mass/2)
    container=create_item_instance(db,definition)
    move_item_instance(db,container,location_type=ItemLocationType.CHARACTER,location_ref=actor.id)
    set_item_owner(db,container,owner_type=ItemOwnerType.CHARACTER,owner_ref=actor.id)
    with pytest.raises(ContainerError):store_item_in_container(db,lot,container)
    assert lot.location_ref==actor.id and lot.quantity==1


def test_stowed_tool_and_wrong_season_do_not_consume_resources(db_session,sampler):
    from app.game.items.equipment import unequip_item,equip_item
    from app.core.enums import EquipmentSlot
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler);before=deepcopy(ind.state)
    unequip_item(db,tool)
    with pytest.raises(ValueError,match="stowed"):service.harvest(db,cid,actor.id,ind.individual_id,p["id"],1,tool.id,"stowed")
    with pytest.raises(ValueError,match="stowed"):service.remove_individual(db,cid,actor.id,ind.individual_id,tool.id,"stowed-removal")
    equip_item(db,tool,slot=EquipmentSlot.MAIN_HAND)
    get_world_time(db,cid).hour=23;db.flush()
    if "noite" not in p["disponibilidade"]["periodos_do_dia"]:
        with pytest.raises(ValueError,match="availability"):service.harvest(db,cid,actor.id,ind.individual_id,p["id"],1,tool.id,"night")
    assert ind.state==before


def test_additive_migration_preserves_zero_weight_legacy_rows():
    import importlib.util
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    p=Path(__file__).resolve().parents[2]/"alembic/versions/v30v3q4r5s6t_plant_resources_r1.py"
    spec=importlib.util.spec_from_file_location("r1_migration",p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=create_engine("sqlite:///:memory:")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE genesis_vegetation_plans (campaign_id VARCHAR PRIMARY KEY)"))
        c.execute(sa.text("CREATE TABLE item_instances (id VARCHAR PRIMARY KEY, quantity INTEGER NOT NULL)"))
        c.execute(sa.text("INSERT INTO item_instances VALUES ('legacy', 3)"))
        with Operations.context(MigrationContext.configure(c)):
            m.upgrade()
            assert tuple(c.execute(sa.text("SELECT quantity,unit_weight_override,weight_authority FROM item_instances")).one())==(3,None,None)
            m.downgrade()
        assert c.execute(sa.text("SELECT quantity FROM item_instances")).scalar()==3
    engine.dispose()


def test_reproductive_parts_require_the_actual_founder_stage(db_session,sampler):
    db=db_session;cid=prepare(db,sampler);initialize_resources(db,cid,experimental=True)
    point,sid=next(candidates(42,"graminea"))
    for slot in range(8):
        ind=service.materialize_individual(db,cid,point,sid,slot)
        seed=next(p for p in sampler.catalog.species[sid].parts() if p["parte"]=="sementes")
        if ind.baseline["phenology"]!="fruiting":break
    assert ind.baseline["phenology"]!="fruiting" and ind.state["part_stock"][seed["id"]]==0
    actor,tool=prepare_operator(db,cid,ind,sampler);set_window(db,cid,seed,ind,sampler)
    with pytest.raises(ValueError,match="stock"):service.harvest(db,cid,actor.id,ind.individual_id,seed["id"],1,tool.id,"immature")
    assert db.query(ItemInstance).filter_by(definition_id=seed["item_id"]).count()==0
