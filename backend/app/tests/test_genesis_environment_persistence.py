from copy import deepcopy
from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from sqlalchemy import text,create_engine,event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_environment import GenesisEnvironmentPlan,GenesisEnvironmentPoint
from app.db.models.world_geology import GenesisMineralDeposit,GenesisGeologicalUnit
from app.db.models.world_geology_regional import GenesisRegionalFormation
from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_climate import GenesisClimatePlan
from app.db.models.region import Region
from app.db.models.subregion import Subregion
from app.game.world.genesis.environment.service import (initialize_environment,get_environment_sampler,
    materialize_environment_point,query_environment,clear_environment_cache)
from app.game.world.genesis.environment.config import EnvironmentConfig
from app.game.world.genesis.environment.water_audit import audit_water_context
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.terrain.service import materialize_terrain_tile
from app.game.world.genesis.terrain.address import tile_at,point_on_face
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign
from app.game.world.genesis.service import initialize_world
from scripts.validate_environment import environment_inputs,import_sources

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def physical():
    sampler=environment_inputs(42,63710000)
    examples=json.loads((ROOT/"artifacts/environment-e1/seed-42-r63710000/examples.json").read_text())
    return sampler,examples


@pytest.fixture(autouse=True)
def caches():
    clear_environment_cache();yield;clear_environment_cache()


def prepare(db,physical):
    sampler,_=physical
    cid=import_sources(db,sampler,42)
    initialize_environment(db,cid)
    return cid


def test_explicit_activation_and_no_silent_legacy_biome_conversion(db_session,physical):
    sampler,examples=physical;point=SurfacePoint(*examples["first_land"]["point"])
    cid=import_sources(db_session,sampler,42)
    assert db_session.get(GenesisEnvironmentPlan,cid) is None
    with pytest.raises(ValueError,match="explicitly"):query_environment(db_session,cid,point)
    initialize_environment(db_session,cid)
    with pytest.raises(ValueError,match="not materialized"):query_environment(db_session,cid,point)
    region=Region(campaign_id=cid,name="legacy region");db_session.add(region);db_session.flush()
    subregion=Subregion(region_id=region.id,name="legacy subregion",biome="FOREST");db_session.add(subregion);db_session.flush()
    materialize_environment_point(db_session,cid,point)
    assert subregion.biome=="FOREST"
    assert db_session.query(GenesisMineralDeposit).count()==0
    with pytest.raises(ValueError,match="reconfigure"):
        initialize_environment(db_session,cid,EnvironmentConfig(cold_regime_max_mean_centi_c=500))
    legacy=create_campaign(db_session,"legacy",world_seed=42);initialize_world(db_session,legacy.id)
    with pytest.raises(ValueError):initialize_environment(db_session,legacy.id)


def test_real_forest_potential_is_persistent_but_not_established_vegetation(db_session,physical):
    _,examples=physical;point=SurfacePoint(*examples["first_forest_potential"]["point"])
    cid=prepare(db_session,physical)
    original=checksum(db_session.get(GenesisClimatePlan,cid).plan),checksum(db_session.get(GenesisWorld,cid).plan)
    row=materialize_environment_point(db_session,cid,point)
    assert row.baseline["persisted_classification"] is True
    forests=[r for r in row.baseline["results"] if r["vegetation_establishment_required"] and r["state"]=="elegivel"]
    assert forests and all(not r["vegetation_confirmed"] for r in forests)
    assert row.baseline["flora_contract"]["vegetation_established"] is None
    assert not row.baseline["constructed_layers"] and not row.baseline["anomalous_layers"]
    assert original==(checksum(db_session.get(GenesisClimatePlan,cid).plan),checksum(db_session.get(GenesisWorld,cid).plan))


def test_real_physical_confirmation_does_not_confirm_unproven_features(db_session,physical):
    _,examples=physical;point=SurfacePoint(*examples["first_physically_confirmable"]["point"])
    cid=prepare(db_session,physical);row=materialize_environment_point(db_session,cid,point)
    confirmed=[r for r in row.baseline["results"] if r["state"]=="confirmado"]
    assert confirmed
    assert all(not r["vegetation_establishment_required"] and not r["confirmation_missing"] and not r["missing"] for r in confirmed)
    assert not any("RIO_" in r["environment_id"] or "CACHOEIRA" in r["environment_id"] for r in confirmed)


def test_reopen_no_reclassification_and_reverse_preparation_order(db_session,physical,monkeypatch):
    _,examples=physical
    points=[SurfacePoint(*examples[k]["point"]) for k in ("first_land","first_forest_potential","first_marine_pending")]
    cid=prepare(db_session,physical)
    stored={p:deepcopy(materialize_environment_point(db_session,cid,p).baseline) for p in reversed(points)}
    db_session.commit();clear_environment_cache()
    def forbidden(*a,**k):raise AssertionError("Saved environmental snapshots must not regenerate")
    monkeypatch.setattr("app.game.world.genesis.environment.adapter.EnvironmentSampler.sample",forbidden)
    with Session(db_session.get_bind()) as reopened:
        for point in points:
            assert materialize_environment_point(reopened,cid,point).baseline==stored[point]
            assert query_environment(reopened,cid,point,baseline_only=True)["baseline"]==stored[point]
        assert reopened.query(GenesisEnvironmentPoint).count()==len(set(points))


def test_exact_face_aliases_share_one_record(db_session,physical):
    cid=prepare(db_session,physical);d=2**30
    a=point_on_face(0,d,d//2,d);b=point_on_face(2,0,d//2,d)
    assert a==b
    first=materialize_environment_point(db_session,cid,a)
    assert materialize_environment_point(db_session,cid,b).probe_id==first.probe_id
    assert db_session.query(GenesisEnvironmentPoint).count()==1


def test_living_world_changes_preserved_and_never_silently_rebuilt(db_session,physical):
    _,examples=physical;point=SurfacePoint(*examples["first_land"]["point"])
    cid=prepare(db_session,physical);row=materialize_environment_point(db_session,cid,point)
    baseline=deepcopy(row.baseline);row.changes={"events":[{"id":"burn-future","kind":"future_overlay"}]}
    with pytest.raises(ValueError,match="overlay"):query_environment(db_session,cid,point)
    assert materialize_environment_point(db_session,cid,point).baseline==baseline
    assert query_environment(db_session,cid,point,baseline_only=True)["changes"]==row.changes


def test_T1_and_JR1_events_invalidate_current_read_without_erasing_history(db_session,physical):
    _,examples=physical;point=SurfacePoint(*examples["first_land"]["point"])
    cid=prepare(db_session,physical);row=materialize_environment_point(db_session,cid,point)
    formation=db_session.get(GenesisRegionalFormation,(cid,row.formation_id))
    formation.changes={"events":[{"id":"formation-change"}]}
    with pytest.raises(ValueError,match="overlay"):query_environment(db_session,cid,point)
    assert query_environment(db_session,cid,point,baseline_only=True)["baseline"]==row.baseline
    formation.changes={};db_session.flush()
    tile=materialize_terrain_tile(db_session,cid,tile_at(point,18));tile.changes={"events":[{"id":"terrain-change"}]}
    with pytest.raises(ValueError,match="overlay"):query_environment(db_session,cid,point)
    assert query_environment(db_session,cid,point,baseline_only=True)["baseline"]==row.baseline


def test_atomic_failure_rolls_back_environment_and_new_geology(db_session,physical):
    _,examples=physical;point=SurfacePoint(*examples["first_land"]["point"])
    cid=prepare(db_session,physical);db_session.commit()
    db_session.execute(text("CREATE TRIGGER e1_fixture_failure BEFORE INSERT ON genesis_environment_points BEGIN SELECT RAISE(ABORT,'synthetic environment write failure'); END"))
    with pytest.raises(IntegrityError):materialize_environment_point(db_session,cid,point)
    assert db_session.query(GenesisEnvironmentPoint).count()==0
    assert db_session.query(GenesisRegionalFormation).count()==0
    assert db_session.query(GenesisGeologicalUnit).count()==0
    db_session.execute(text("DROP TRIGGER e1_fixture_failure"));db_session.commit()
    materialize_environment_point(db_session,cid,point);db_session.rollback()
    assert db_session.query(GenesisEnvironmentPoint).count()==0
    assert db_session.query(GenesisRegionalFormation).count()==0


def test_concurrent_sessions_cannot_duplicate_classification(tmp_path,physical):
    _,examples=physical;point=SurfacePoint(*examples["first_land"]["point"])
    engine=create_engine(f"sqlite:///{(tmp_path/'e1-concurrent.db').as_posix()}")
    event.listen(engine,"connect",enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid=prepare(db,physical);db.commit()
    with Session(engine) as a,Session(engine) as b:
        get_environment_sampler(b,cid)
        one=materialize_environment_point(a,cid,point);identifier=one.probe_id;a.commit()
        two=materialize_environment_point(b,cid,point);b.commit()
        assert two.probe_id==identifier
        assert b.query(GenesisEnvironmentPoint).count()==1
    engine.dispose()


def test_checksum_version_and_reset_scoping(db_session,physical):
    _,examples=physical;point=SurfacePoint(*examples["first_land"]["point"])
    first=prepare(db_session,physical);second=prepare(db_session,physical)
    row=materialize_environment_point(db_session,first,point);materialize_environment_point(db_session,second,point)
    saved=deepcopy(row.baseline);row.baseline={**row.baseline,"primary_potential":"invented"}
    with pytest.raises(ValueError,match="mismatch"):query_environment(db_session,first,point,baseline_only=True)
    row.baseline=saved
    header=db_session.get(GenesisEnvironmentPlan,first);header.environment_version=2
    with pytest.raises(ValueError,match="version"):get_environment_sampler(db_session,first)
    header.environment_version=1;db_session.flush();delete_campaign(db_session,first)
    assert db_session.query(GenesisEnvironmentPlan).filter_by(campaign_id=first).count()==0
    assert db_session.query(GenesisEnvironmentPoint).filter_by(campaign_id=second).count()==1


def test_positive_real_P1_flow_does_not_become_vegetation_or_perennial_river(db_session,physical):
    from app.tests.test_genesis_practical_hydrology_persistence import prepare as prepare_p1,allocation_request,flow_request
    from app.game.world.genesis.water_reconciliation.service import reconcile
    cid,_,_,proof,evidence=prepare_p1(db_session)
    reconcile(db_session,cid,allocation_request(db_session,cid,proof,evidence))
    moved=reconcile(db_session,cid,flow_request(db_session,cid,proof,evidence))
    assert moved.payload["local_reconciliation"]["delivered_liters"]==19
    point=SurfacePoint(*proof["points"][0]);audit=audit_water_context(db_session,cid,point)
    assert audit["W1_present"] and audit["W2_present"] and audit["P1_present"]
    assert audit["W1_final_macro_surface_liters"]>0
    assert audit["local_permanent_water_confirmed"] is audit["vegetation_evidence"] is None
    sample=physical[0].sample(point)
    assert sample["logical_facts"]["hidrologia.rede_fluvial_confirmada"] is None
    assert sample["flora_contract"]["vegetation_established"] is None


def test_environment_read_is_independent_of_pending_mineral_depletion(db_session,physical):
    from app.game.world.genesis.geology.regional.service import materialize_regional_formation
    proof=json.loads((ROOT/"artifacts/geology-jr1/seed-42-r63710000-w0/persistent-proof.json").read_text())
    point=SurfacePoint(*proof["result"]["formation"]["anchor_point"])
    cid=prepare(db_session,physical)
    materialize_regional_formation(db_session,cid,point,experimental_sources=True)
    row=materialize_environment_point(db_session,cid,point)
    original=deepcopy(row.baseline)
    source=db_session.query(GenesisMineralDeposit).filter_by(campaign_id=cid).first()
    assert source is not None
    source.remaining_units=0
    assert query_environment(db_session,cid,point)["baseline"]==original
    assert source.remaining_units==0


def test_additive_migration_and_downgrade_preserve_JR1(tmp_path):
    path=tmp_path/"e1-migration.db";env={**os.environ,"DATABASE_URL":f"sqlite:///{path.as_posix()}"}
    def migrate(direction,target):
        subprocess.run([sys.executable,"-m","alembic",direction,target],cwd=ROOT/"backend",env=env,
            capture_output=True,text=True,check=True)
    migrate("upgrade","s27s0n1o2p3q")
    with sqlite3.connect(path) as db:
        before=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        db.execute("INSERT INTO genesis_regional_geology(campaign_id,regional_version,signature,descriptor,policy,policy_signature,source_checksum,write_epoch) VALUES ('old',1,'sig','{\"sentinel\":1}','{}','p','s',0)")
    migrate("upgrade","t28t1o2p3q4r")
    with sqlite3.connect(path) as db:
        after=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert all(after[k]==v for k,v in before.items())
        assert db.execute("SELECT COUNT(*) FROM genesis_environment_plans").fetchone()[0]==0
    migrate("downgrade","s27s0n1o2p3q")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT descriptor FROM genesis_regional_geology WHERE campaign_id='old'").fetchone()[0]=='{"sentinel":1}'
