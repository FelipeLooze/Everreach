import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from sqlalchemy.orm import Session
from app.db.models.world_geology import GenesisGeologyPlan, GenesisGeologicalUnit, GenesisMineralDeposit
from app.db.models.world_genesis import GenesisWorld
from app.game.world.seed import create_campaign
from app.game.world.reset import delete_campaign
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.terrain.service import initialize_terrain
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.geology.config import GeologyConfig
from app.game.world.genesis.geology.calibration import select_test_deposits, ExperimentalCalibration
from app.game.world.genesis.geology.service import (initialize_geology,get_geology_plan,
    materialize_geological_unit,query_geology,materialize_test_deposit)

ROOT = Path(__file__).resolve().parents[3]


def prepare(db, seed=0):
    campaign = create_campaign(db,"J1 test",world_seed=seed)
    initialize_world(db,campaign.id,FormationConfigV4())
    initialize_terrain(db,campaign.id)
    initialize_geology(db,campaign.id)
    return campaign.id,get_geology_plan(db,campaign.id)


def test_explicit_opt_in_no_world_or_query_side_effects(db_session):
    campaign = create_campaign(db_session,"new",world_seed=42)
    initialize_world(db_session,campaign.id,FormationConfigV4())
    initialize_terrain(db_session,campaign.id)
    assert db_session.get(GenesisGeologyPlan,campaign.id) is None
    with pytest.raises(ValueError,match="explicitly"):
        query_geology(db_session,campaign.id,SurfacePoint(1,0,0))
    initialize_geology(db_session,campaign.id)
    query_geology(db_session,campaign.id,SurfacePoint(1,0,0))
    assert db_session.query(GenesisGeologicalUnit).count() == 0
    assert db_session.query(GenesisMineralDeposit).count() == 0
    with pytest.raises(ValueError,match="reconfigure"):
        initialize_geology(db_session,campaign.id,GeologyConfig(expected_provinces=64))
    legacy = create_campaign(db_session,"legacy",world_seed=42)
    initialize_world(db_session,legacy.id)
    with pytest.raises(ValueError):
        initialize_geology(db_session,legacy.id)


def test_real_deposit_is_finite_and_does_not_respawn_after_reopen(db_session,monkeypatch):
    cid,plan = prepare(db_session)
    world = db_session.get(GenesisWorld,cid)
    old = checksum(world.plan)
    proposals = select_test_deposits(plan)
    assert len(proposals) == 3
    proposal = proposals[0]
    with pytest.raises(ValueError,match="disabled"):
        materialize_test_deposit(db_session,cid,proposal["deposit_id"])
    with pytest.raises(ValueError,match="Sensitivity"):
        materialize_test_deposit(db_session,cid,proposal["deposit_id"],experimental=True,
                                 calibration=ExperimentalCalibration(rate_factor_ppm=2000000))
    with pytest.raises(ValueError,match="not selected"):
        materialize_test_deposit(db_session,cid,"fabricated",experimental=True)
    row = materialize_test_deposit(db_session,cid,proposal["deposit_id"],experimental=True)
    initial = row.remaining_units
    host = next(u for u in plan.units if u["geological_unit_id"] == proposal["geological_unit_id"])
    assessment = query_geology(db_session,cid,SurfacePoint(*host["center"]))["assessment"]
    assert initial > 0 and row.baseline["material_id"] in {o["material_id"] for o in assessment["opportunities"]}
    row.remaining_units = 0  # future extraction consumer; no inventory is fabricated here
    db_session.commit()
    def forbidden(*a,**kw):
        raise AssertionError("Established geology must not reconstruct")
    monkeypatch.setattr("app.game.world.genesis.geology.field.reconstruct",forbidden)
    with Session(db_session.get_bind()) as reopened:
        saved = materialize_test_deposit(reopened,cid,proposal["deposit_id"],experimental=True)
        assert saved.remaining_units == 0
        assert saved.baseline["initial_volume_units"] == initial
        assert reopened.query(GenesisMineralDeposit).count() == 1
        assert checksum(reopened.get(GenesisWorld,cid).plan) == old


def test_progressive_units_order_events_and_reloads(db_session,monkeypatch):
    cid,plan = prepare(db_session,42)
    first = [SurfacePoint(*u["center"]) for u in plan.units[:4]]
    ids = [materialize_geological_unit(db_session,cid,p).unit_id for p in first]
    assert [materialize_geological_unit(db_session,cid,p).unit_id for p in reversed(first)] == list(reversed(ids))
    assert db_session.query(GenesisGeologicalUnit).count() == 4
    unit = db_session.get(GenesisGeologicalUnit,(cid,ids[0]))
    original = json.loads(json.dumps(unit.baseline))
    unit.changes = {"events":[{"id":"excavation-future","kind":"uninterpreted"}]}
    db_session.commit()
    def forbidden(*a,**kw):
        raise AssertionError("No history generation on revisit")
    monkeypatch.setattr("app.game.world.genesis.geology.field.reconstruct",forbidden)
    with Session(db_session.get_bind()) as reopened:
        assert materialize_geological_unit(reopened,cid,first[0]).baseline == original
        with pytest.raises(ValueError,match="overlay"):
            query_geology(reopened,cid,first[0])
        assert query_geology(reopened,cid,first[0],baseline_only=True)["unit"] == original
        # Unvisited units do not alter the established histories.
        materialize_geological_unit(reopened,cid,SurfacePoint(*plan.units[20]["center"]))
        assert materialize_geological_unit(reopened,cid,first[0]).baseline == original


def test_corrupt_authority_and_unit_rejected(db_session):
    cid,plan = prepare(db_session)
    unit = materialize_geological_unit(db_session,cid,SurfacePoint(*plan.units[0]["center"]))
    unit.baseline = {**unit.baseline,"thickness_m":999999}
    with pytest.raises(ValueError,match="mismatch"):
        materialize_geological_unit(db_session,cid,SurfacePoint(*plan.units[0]["center"]))
    authority = db_session.get(GenesisGeologyPlan,cid)
    authority.geology_version = 2
    with pytest.raises(ValueError,match="version"):
        get_geology_plan(db_session,cid)


def test_rollback_and_scoped_reset(db_session):
    cid,plan = prepare(db_session)
    other,other_plan = prepare(db_session,42)
    materialize_geological_unit(db_session,other,SurfacePoint(*other_plan.units[0]["center"]))
    db_session.commit()
    proposal = select_test_deposits(plan)[0]
    materialize_test_deposit(db_session,cid,proposal["deposit_id"],experimental=True)
    db_session.rollback()
    assert db_session.query(GenesisMineralDeposit).count() == 0
    assert db_session.query(GenesisGeologicalUnit).filter_by(campaign_id=cid).count() == 0
    materialize_test_deposit(db_session,cid,proposal["deposit_id"],experimental=True)
    delete_campaign(db_session,cid)
    assert db_session.query(GenesisGeologyPlan).filter_by(campaign_id=cid).count() == 0
    assert db_session.query(GenesisMineralDeposit).count() == 0
    assert db_session.query(GenesisGeologicalUnit).filter_by(campaign_id=other).count() == 1


def test_additive_migration_preserves_old_authority_and_downgrades(tmp_path):
    path = tmp_path/"j1-migration.db"
    env = {**os.environ,"DATABASE_URL":f"sqlite:///{path.as_posix()}"}
    def migrate(direction,target):
        subprocess.run([sys.executable,"-m","alembic",direction,target],cwd=ROOT/"backend",env=env,
                       capture_output=True,text=True,check=True)
    migrate("upgrade","q25q8l9m0n1o")
    with sqlite3.connect(path) as db:
        before = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        db.execute("INSERT INTO genesis_terrain_plans(campaign_id,terrain_version,signature,source_checksum,config,plan) VALUES ('old',1,'old','hash','{}','{\"sentinel\":1}')")
    migrate("upgrade","r26r9m0n1o2p")
    with sqlite3.connect(path) as db:
        after = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert all(after[k] == v for k,v in before.items())
        assert db.execute("SELECT COUNT(*) FROM genesis_geology_plans").fetchone()[0] == 0
    migrate("downgrade","q25q8l9m0n1o")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT plan FROM genesis_terrain_plans WHERE campaign_id='old'").fetchone()[0] == '{"sentinel":1}'
