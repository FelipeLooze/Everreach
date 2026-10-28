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
from app.db.models.world_geology import GenesisGeologyPlan,GenesisGeologicalUnit,GenesisMineralDeposit
from app.db.models.world_geology_regional import GenesisRegionalGeology,GenesisRegionalFormation,GenesisRegionalSource
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.terrain.service import initialize_terrain,materialize_terrain_tile
from app.game.world.genesis.terrain.address import tile_at
from app.game.world.genesis.geology.service import initialize_geology,materialize_test_deposit
from app.game.world.genesis.geology.calibration import select_test_deposits
from app.game.world.genesis.geology.regional.service import (initialize_regional_geology,materialize_regional_formation,
    query_regional_geology,context)
from app.game.world.genesis.geology.regional.config import RegionalConfig,RegionalPolicy
from app.game.world.genesis.geology.regional.experiment import cross_sector_points
from app.game.world.genesis.geology.regional.occurrence import select_sources
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.terrain.field import checksum
from app.game.world.seed import create_campaign
from app.game.world.reset import delete_campaign
from scripts.validate_regional_geology import inputs,land_windows

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def actual():
    sampler=inputs(42,63710000)
    from app.game.world.genesis.geology.regional.experiment import window_formations
    forms,_=window_formations(sampler,land_windows(sampler)[0])
    for f in forms.values():
        selected=select_sources(f,sampler.signature)
        witness=cross_sector_points(sampler,f) if selected else None
        if witness:
            return sampler,f,selected,witness
    raise AssertionError("Real bounded reference lacks a source-bearing sector crossing")


def prepare(db,seed=42):
    campaign=create_campaign(db,"JR1 tests",world_seed=seed)
    initialize_world(db,campaign.id,FormationConfigV4())
    initialize_terrain(db,campaign.id);initialize_geology(db,campaign.id)
    return campaign.id


def test_explicit_activation_and_no_sources_from_query(db_session,actual):
    _,f,_,witness=actual;point=SurfacePoint(*witness[0]["point"])
    cid=prepare(db_session)
    assert db_session.get(GenesisRegionalGeology,cid) is None
    with pytest.raises(ValueError,match="explicitly"):
        query_regional_geology(db_session,cid,point)
    initialize_regional_geology(db_session,cid)
    with pytest.raises(ValueError,match="not materialized"):
        query_regional_geology(db_session,cid,point)
    materialize_regional_formation(db_session,cid,point)
    result=query_regional_geology(db_session,cid,point)
    assert result["formation"]==f and result["sources"]==[]
    assert db_session.query(GenesisMineralDeposit).count()==0
    with pytest.raises(ValueError,match="reconfigure"):
        initialize_regional_geology(db_session,cid,RegionalConfig(formation_spacing_m=16000))
    with pytest.raises(ValueError,match="reconfigure"):
        initialize_regional_geology(db_session,cid,policy=RegionalPolicy(rate_factor_ppm=500000))


def test_real_shared_finite_stock_reopen_and_no_regeneration(db_session,actual,monkeypatch):
    _,f,selected,witness=actual
    cid=prepare(db_session);initialize_regional_geology(db_session,cid)
    before=checksum(db_session.get(GenesisGeologyPlan,cid).baseline)
    a,b=[SurfacePoint(*p["point"]) for p in witness]
    materialize_regional_formation(db_session,cid,a,experimental_sources=True)
    first=query_regional_geology(db_session,cid,a)
    assert len(first["sources"])==len(selected)>0
    assert db_session.query(GenesisRegionalFormation).count()==1
    chosen=first["sources"][0]
    source=db_session.get(GenesisMineralDeposit,(cid,chosen["deposit_id"]))
    initial=source.remaining_units;source.remaining_units=0
    db_session.flush();db_session.commit()
    def forbidden(*args,**kwargs):
        raise AssertionError("Established regional formations must not rebuild history")
    monkeypatch.setattr("app.game.world.genesis.geology.regional.field.RegionalSampler._build",forbidden)
    with Session(db_session.get_bind()) as reopened:
        materialize_regional_formation(reopened,cid,b,experimental_sources=True)
        result=query_regional_geology(reopened,cid,b)
        assert result["formation"]==f
        assert next(s["remaining_units"] for s in result["sources"] if s["deposit_id"]==source.deposit_id)==0
        assert initial==next(s["baseline"]["initial_volume_units"] for s in result["sources"] if s["deposit_id"]==source.deposit_id)
        assert reopened.query(GenesisRegionalFormation).count()==1
        assert reopened.query(GenesisMineralDeposit).count()==len(selected)
        assert checksum(reopened.get(GenesisGeologyPlan,cid).baseline)==before


def test_event_and_corruption_fail_closed_preserving_history(db_session,actual):
    _,_,_,witness=actual;point=SurfacePoint(*witness[0]["point"])
    cid=prepare(db_session);initialize_regional_geology(db_session,cid)
    row=materialize_regional_formation(db_session,cid,point,experimental_sources=True)
    original=json.loads(json.dumps(row.baseline))
    row.changes={"events":[{"id":"regional-excavation","kind":"future_overlay"}]}
    with pytest.raises(ValueError,match="overlay"):
        query_regional_geology(db_session,cid,point)
    assert query_regional_geology(db_session,cid,point,baseline_only=True)["formation"]==original
    with pytest.raises(ValueError,match="reconciliation"):
        materialize_regional_formation(db_session,cid,point,experimental_sources=True)
    row.changes={};row.baseline={**row.baseline,"thickness_m":999999}
    with pytest.raises(ValueError,match="mismatch"):
        query_regional_geology(db_session,cid,point)


def test_parent_and_terrain_events_are_not_ignored(db_session,actual):
    _,f,_,witness=actual;point=SurfacePoint(*witness[0]["point"])
    cid=prepare(db_session);initialize_regional_geology(db_session,cid)
    row=materialize_regional_formation(db_session,cid,point)
    parent=db_session.get(GenesisGeologicalUnit,(cid,row.parent_unit_id))
    parent.changes={"events":[{"id":"parent-event"}]}
    with pytest.raises(ValueError,match="Parent geological"):
        query_regional_geology(db_session,cid,point)
    assert query_regional_geology(db_session,cid,point,baseline_only=True)["formation"]==f
    parent.changes={}
    anchor=SurfacePoint(*f["anchor_point"])
    tile=materialize_terrain_tile(db_session,cid,tile_at(anchor,18))
    tile.changes={"events":[{"id":"landslide"}]}
    with pytest.raises(ValueError,match="overlay"):
        materialize_regional_formation(db_session,cid,point,experimental_sources=True)
    assert db_session.query(GenesisMineralDeposit).count()==0


def test_atomic_source_failure_and_outer_rollback(db_session,actual):
    _,_,_,witness=actual;point=SurfacePoint(*witness[0]["point"])
    cid=prepare(db_session);initialize_regional_geology(db_session,cid);db_session.commit()
    db_session.execute(text("CREATE TRIGGER jr1_fixture_failure BEFORE INSERT ON genesis_regional_sources BEGIN SELECT RAISE(ABORT,'synthetic link failure'); END"))
    with pytest.raises(IntegrityError):
        materialize_regional_formation(db_session,cid,point,experimental_sources=True)
    assert db_session.query(GenesisMineralDeposit).count()==0
    assert db_session.query(GenesisRegionalFormation).count()==0
    assert db_session.query(GenesisRegionalSource).count()==0
    db_session.execute(text("DROP TRIGGER jr1_fixture_failure"));db_session.commit()
    materialize_regional_formation(db_session,cid,point,experimental_sources=True)
    db_session.rollback()
    assert db_session.query(GenesisMineralDeposit).count()==0
    assert db_session.query(GenesisRegionalFormation).count()==0


def test_two_sessions_cannot_duplicate_the_same_physical_sources(tmp_path,actual):
    _,_,selected,witness=actual;a,b=[SurfacePoint(*v["point"]) for v in witness]
    engine=create_engine(f"sqlite:///{(tmp_path/'jr1-concurrency.db').as_posix()}")
    event.listen(engine,"connect",enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid=prepare(db);initialize_regional_geology(db,cid);db.commit()
    with Session(engine) as first,Session(engine) as second:
        context(second,cid)
        materialize_regional_formation(first,cid,a,experimental_sources=True);first.commit()
        materialize_regional_formation(second,cid,b,experimental_sources=True);second.commit()
        assert second.query(GenesisMineralDeposit).count()==len(selected)
        assert second.query(GenesisRegionalSource).count()==len(selected)
        assert second.query(GenesisRegionalFormation).count()==1
    engine.dispose()


def test_macro_allocated_sources_require_explicit_migration(db_session):
    cid=prepare(db_session,0)
    from app.game.world.genesis.geology.service import get_geology_plan
    selected=select_test_deposits(get_geology_plan(db_session,cid))
    saved=materialize_test_deposit(db_session,cid,selected[0]["deposit_id"],experimental=True)
    old=saved.remaining_units
    with pytest.raises(ValueError,match="allocation migration"):
        initialize_regional_geology(db_session,cid)
    assert saved.remaining_units==old and db_session.get(GenesisRegionalGeology,cid) is None


def test_active_JR1_cannot_also_generate_macro_experimental_reserves(db_session):
    cid=prepare(db_session,0);initialize_regional_geology(db_session,cid)
    from app.game.world.genesis.geology.service import get_geology_plan
    selected=select_test_deposits(get_geology_plan(db_session,cid))
    with pytest.raises(ValueError,match="JR1 is active"):
        materialize_test_deposit(db_session,cid,selected[0]["deposit_id"],experimental=True)
    assert db_session.query(GenesisMineralDeposit).count()==0


def test_original_J1_source_path_still_works_without_JR1_tables(db_session):
    cid=prepare(db_session,0)
    from app.game.world.genesis.geology.service import get_geology_plan
    selected=select_test_deposits(get_geology_plan(db_session,cid))
    for name in ("genesis_regional_sources","genesis_regional_formations","genesis_regional_geology"):
        db_session.execute(text(f"DROP TABLE {name}"))
    source=materialize_test_deposit(db_session,cid,selected[0]["deposit_id"],experimental=True)
    assert source.remaining_units==source.baseline["initial_volume_units"]>0


def test_policy_checksum_and_stock_changes_not_discarded(db_session,actual):
    _,_,_,witness=actual;point=SurfacePoint(*witness[0]["point"])
    cid=prepare(db_session);header=initialize_regional_geology(db_session,cid)
    materialize_regional_formation(db_session,cid,point,experimental_sources=True)
    source=db_session.query(GenesisMineralDeposit).first();source.remaining_units=0
    with pytest.raises(ValueError,match="Flush"):
        query_regional_geology(db_session,cid,point)
    assert source.remaining_units==0
    db_session.flush()
    assert any(s["remaining_units"]==0 for s in query_regional_geology(db_session,cid,point)["sources"])
    header.policy={**header.policy,"rate_factor_ppm":2000000}
    with pytest.raises(ValueError,match="policy mismatch"):
        context(db_session,cid)


def test_reset_is_scoped_and_removes_child_links_first(db_session,actual):
    _,_,_,witness=actual;point=SurfacePoint(*witness[0]["point"])
    first=prepare(db_session);second=prepare(db_session)
    for cid in (first,second):
        initialize_regional_geology(db_session,cid)
        materialize_regional_formation(db_session,cid,point,experimental_sources=True)
    delete_campaign(db_session,first)
    assert db_session.get(GenesisRegionalGeology,first) is None
    assert db_session.query(GenesisRegionalSource).filter_by(campaign_id=first).count()==0
    assert db_session.query(GenesisMineralDeposit).filter_by(campaign_id=first).count()==0
    assert db_session.query(GenesisRegionalSource).filter_by(campaign_id=second).count()>0


def test_additive_upgrade_and_downgrade_preserve_existing_J1(tmp_path):
    path=tmp_path/"jr1-migration.db";env={**os.environ,"DATABASE_URL":f"sqlite:///{path.as_posix()}"}
    def migrate(direction,target):
        subprocess.run([sys.executable,"-m","alembic",direction,target],cwd=ROOT/"backend",env=env,
            capture_output=True,text=True,check=True)
    migrate("upgrade","r26r9m0n1o2p")
    with sqlite3.connect(path) as db:
        before=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        db.execute("INSERT INTO genesis_geology_plans(campaign_id,geology_version,signature,baseline,baseline_checksum) VALUES ('old',1,'sig','{\"sentinel\":1}','hash')")
    migrate("upgrade","s27s0n1o2p3q")
    with sqlite3.connect(path) as db:
        after=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert all(after[k]==v for k,v in before.items())
        assert db.execute("SELECT COUNT(*) FROM genesis_regional_geology").fetchone()[0]==0
    migrate("downgrade","r26r9m0n1o2p")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT baseline FROM genesis_geology_plans WHERE campaign_id='old'").fetchone()[0]=='{"sentinel":1}'
