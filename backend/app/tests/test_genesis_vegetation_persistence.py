from copy import deepcopy
import json
import pytest
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_vegetation import GenesisVegetationCommunity,GenesisPlantIndividual,GenesisPlantAction,GenesisBotanicalToolCertificate
from app.db.models.item import ItemInstance
from app.db.models.world_environment import GenesisEnvironmentPlan
from app.db.models.character import Character
from app.game.world.genesis.vegetation import service as vg
from app.game.world.genesis.vegetation.config import VegetationConfig
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.time.clock import get_world_time
from scripts.prove_vegetation import prepare,find_collectable,actor_at
from scripts.validate_vegetation import inputs_vg1,centers


@pytest.fixture(scope="module")
def vegetation():return inputs_vg1(42,"exploration_mosaic_v1")


def setup_plot(db,v):
    cid=prepare(db,v);point,sid=find_collectable(v)
    ind=vg.materialize_individual(db,cid,point,sid,0)
    actor,tool=actor_at(db,cid,ind,v)
    part=next(p for p in v.catalog.species[sid].parts() if ind.state["part_stock"].get(p["id"],0)>0)
    clock=get_world_time(db,cid)
    clock.month={"primavera":3,"verao":6,"outono":9,"inverno":12}[part["disponibilidade"]["estacoes"][0]]
    clock.hour={"manha":8,"tarde":14,"noite":22}[part["disponibilidade"]["periodos_do_dia"][0]]
    db.flush();return cid,point,sid,ind,actor,tool,part


def test_no_automatic_activation_or_generation(db_session,vegetation):
    from scripts.validate_water_c3 import import_disposable,ROOT
    v=vegetation;regions=json.loads((ROOT/"artifacts/water-c3-compatibility/seed-42/C3-hr1-evidence.json").read_text())
    cid,_=import_disposable(db_session,v.environment,v.water,regions)
    with pytest.raises(ValueError,match="experimental"):vg.initialize_vegetation(db_session,cid)
    from app.game.world.genesis.environment.service import initialize_environment
    from app.game.world.genesis.environment.config import EnvironmentConfigC3
    initialize_environment(db_session,cid,EnvironmentConfigC3())
    vg.initialize_vegetation(db_session,cid,v.config,experimental=True)
    assert db_session.query(GenesisVegetationCommunity).count()==db_session.query(GenesisPlantIndividual).count()==0
    with pytest.raises(ValueError,match="not materialized"):vg.query_community(db_session,cid,centers(42)["moderate"])
    with pytest.raises(ValueError,match="reconfigure"):vg.initialize_vegetation(db_session,cid,VegetationConfig(),experimental=True)


def test_collection_finite_idempotent_no_regrowth_after_commit_and_reopen(tmp_path,vegetation):
    engine=create_engine("sqlite:///"+str(tmp_path/"plants.sqlite"));event.listen(engine,"connect",enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid,p,sid,ind,actor,tool,part=setup_plot(db,vegetation);iid=ind.individual_id;aid=actor.id;tid=tool.id
        initial=deepcopy(ind.state)
        receipt=vg.harvest(db,cid,aid,iid,part["id"],1,tid,"h1")
        assert receipt==vg.harvest(db,cid,aid,iid,part["id"],1,tid,"h1")
        assert receipt["stock_after"][part["id"]]==initial["part_stock"][part["id"]]-1
        with pytest.raises(ValueError):vg.harvest(db,cid,aid,iid,part["id"],2,tid,"h1")
        with pytest.raises(ValueError,match="stock|removed"):vg.harvest(db,cid,aid,iid,part["id"],99999,tid,"exhaust")
        assert db.query(ItemInstance).filter_by(definition_id=part["item_id"],location_ref=aid).count()==1
        if ind.state["alive"]:vg.remove_individual(db,cid,aid,iid,tid,"remove")
        db.commit()
    with Session(engine) as db:
        revisited=vg.materialize_individual(db,cid,p,sid,0)
        assert revisited.individual_id==iid and not revisited.state["alive"] and not any(revisited.state["part_stock"].values())
        assert vg.query_community(db,cid,p)["removed_individuals"][sid]==1
        with pytest.raises(ValueError,match="removed"):vg.harvest(db,cid,aid,iid,part["id"],1,tid,"after-removal")
        assert db.query(ItemInstance).filter_by(definition_id=part["item_id"]).one().quantity==1
        assert vg.harvest(db,cid,aid,iid,part["id"],1,tid,"h1")==receipt
    engine.dispose()


def test_presence_identification_fine_capability_and_season_gates(db_session,vegetation):
    db=db_session;cid,p,sid,ind,actor,tool,part=setup_plot(db,vegetation)
    assert vg.observe_individual(db,cid,actor.id,ind.individual_id)["identified"]
    from app.db.models.skill import CharacterSkill
    skill=db.query(CharacterSkill).filter_by(character_id=actor.id,skill_id="EV-PROF-BOT-001").one();skill.mastery=0;db.flush()
    observation=vg.observe_individual(db,cid,actor.id,ind.individual_id)
    assert observation["name"] is None and observation["species_id"] is None
    cert=db.get(GenesisBotanicalToolCertificate,tool.definition_id);db.delete(cert);db.flush()
    initial=deepcopy(ind.state)
    with pytest.raises(ValueError,match="capabilities"):vg.harvest(db,cid,actor.id,ind.individual_id,part["id"],1,tool.id,"uncertified")
    assert ind.state==initial and db.query(GenesisPlantAction).count()==0
    original_location=actor.location_id;actor.location_id=None;db.flush()
    with pytest.raises(ValueError,match="anchored"):vg.observe_individual(db,cid,actor.id,ind.individual_id)
    actor.location_id=original_location


def test_corrupted_community_and_individual_never_regenerated(db_session,vegetation):
    db=db_session;cid,p,sid,ind,actor,tool,part=setup_plot(db,vegetation)
    state=deepcopy(ind.state);state["part_stock"][part["id"]]+=100;ind.state=state;db.flush()
    with pytest.raises(ValueError,match="corrupted"):vg.materialize_individual(db,cid,p,sid,0)
    db.rollback()


def test_outer_rollback_removes_every_new_materialization(db_session,vegetation):
    db=db_session;cid=prepare(db,vegetation);db.commit()
    p=centers(42)["moderate"]
    vg.materialize_community(db,cid,p)
    assert db.query(GenesisVegetationCommunity).count()==1
    db.rollback()
    assert db.query(GenesisVegetationCommunity).count()==0


def test_finite_slots_and_read_does_not_create_individuals(db_session,vegetation):
    db=db_session;cid=prepare(db,vegetation);p=centers(42)["moderate"]
    community=vg.materialize_community(db,cid,p);pop=community.baseline["populations"][0]
    with pytest.raises(ValueError,match="finite"):vg.materialize_individual(db,cid,p,pop["species_id"],pop["founder_count"])
    with pytest.raises(ValueError,match="finite"):vg.materialize_individual(db,cid,p,pop["species_id"],True)
    assert db.query(GenesisPlantIndividual).count()==0
    vg.query_community(db,cid,p)
    assert db.query(GenesisPlantIndividual).count()==0


def test_unknown_catalog_stock_never_becomes_a_collectible_resource(db_session,vegetation):
    db=db_session;cid=prepare(db,vegetation);p=centers(42)["moderate"]
    community=vg.materialize_community(db,cid,p)
    pop=next(x for x in community.baseline["populations"] if vegetation.catalog.species[x["species_id"]].stock is None)
    ind=vg.materialize_individual(db,cid,p,pop["species_id"],0)
    assert ind.baseline["stock_calibration"]=="pending_catalog_stock"
    assert not any(ind.state["part_stock"].values())


def test_campaign_delete_includes_opt_in_vegetation_only(db_session,vegetation):
    from app.game.world.reset import delete_campaign
    from app.game.world.seed import create_campaign
    db=db_session;cid,p,sid,ind,actor,tool,part=setup_plot(db,vegetation)
    vg.harvest(db,cid,actor.id,ind.individual_id,part["id"],1,tool.id,"delete-proof")
    kept=create_campaign(db,"unchanged legacy campaign",world_seed=7);kept_id=kept.id
    assert delete_campaign(db,cid)
    db.flush()
    assert db.query(GenesisVegetationCommunity).count()==db.query(GenesisPlantIndividual).count()==db.query(GenesisPlantAction).count()==0
    from app.db.models.campaign import Campaign
    assert db.get(Campaign,kept_id) is not None


def test_corrupted_community_or_pinned_plan_is_refused(db_session,vegetation):
    from app.db.models.world_vegetation import GenesisVegetationPlan
    db=db_session;cid=prepare(db,vegetation);p=centers(42)["moderate"]
    community=vg.materialize_community(db,cid,p);data=deepcopy(community.baseline)
    data["cover_ppm"]+=1;community.baseline=data;db.flush()
    with pytest.raises(ValueError,match="corrupted"):vg.query_community(db,cid,p)
    plan=db.get(GenesisVegetationPlan,cid);data=deepcopy(plan.descriptor)
    data["config"]["mosaic_m"]+=1;plan.descriptor=data;db.flush()
    with pytest.raises(ValueError,match="descriptor corrupted"):vg.context(db,cid)


def test_alembic_vegetation_upgrade_and_downgrade_only_in_temporary_database():
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    file=Path(__file__).resolve().parents[2]/"alembic/versions/u29u2p3q4r5s_add_vegetation_vg1.py"
    spec=importlib.util.spec_from_file_location("vegetation_migration",file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        for table,column in (("genesis_environment_plans","campaign_id"),("characters","id"),("item_tool_profiles","item_id")):
            conn.execute(sa.text(f"CREATE TABLE {table} ({column} VARCHAR PRIMARY KEY)"))
        before=set(sa.inspect(conn).get_table_names())
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            assert len(set(sa.inspect(conn).get_table_names())-before)==5
            for name in ("genesis_vegetation_plans","genesis_vegetation_communities","genesis_plant_individuals","genesis_plant_actions","genesis_botanical_tool_certificates"):
                assert {c["name"] for c in sa.inspect(conn).get_columns(name)}==set(Base.metadata.tables[name].columns.keys())
            module.downgrade()
        assert set(sa.inspect(conn).get_table_names())==before
    engine.dispose()


def test_actual_founder_tree_cut_stays_removed_without_inventing_timber(db_session,vegetation):
    db=db_session;cid=prepare(db,vegetation);point=centers(42)["wet"]
    community=vg.materialize_community(db,cid,point)
    pop=next(p for p in community.baseline["populations"] if p["kind"]=="arvore")
    ind=vg.materialize_individual(db,cid,point,pop["species_id"],0)
    actor,tool=actor_at(db,cid,ind,vegetation);before=db.query(ItemInstance).count()
    receipt=vg.remove_individual(db,cid,actor.id,ind.individual_id,tool.id,"cut-founder-tree")
    assert receipt["items_created"]==0 and db.query(ItemInstance).count()==before
    revisited=vg.materialize_individual(db,cid,point,pop["species_id"],0)
    assert not revisited.state["alive"]
    current=vg.query_community(db,cid,point)
    changed=next(p for p in current["populations"] if p["species_id"]==pop["species_id"])
    assert changed["living_count"]==pop["founder_count"]-1
