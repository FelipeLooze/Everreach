from copy import deepcopy
import json
from pathlib import Path
import pytest
from sqlalchemy.orm import Session
from app.db.models.world_hydro_geometry import GenesisHydroGeometryEvidence
from app.db.models.world_practical_hydrology import GenesisLocalWaterAccount, GenesisPracticalCapacityUse
from app.db.models.world_water_reconciliation import GenesisWaterDomain, GenesisWaterRevision
from scripts.preview_water_reconciliation import import_snapshots
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.water_reconciliation.config import RevisionRequest, TransferIntent
from app.game.world.genesis.water_reconciliation.service import (initialize_reconciliation, prepare_water_domain,
    get_water_domain, get_revision, reconcile)
from app.game.world.genesis.water_reconciliation.practical.config import PracticalConfig
from app.game.world.genesis.water_reconciliation.practical.service import (initialize_practical_hydrology,
    prepare_natural_passage, get_local_account, POOL)

ROOT = Path(__file__).resolve().parents[3]


def prepare(db):
    proof = json.loads((ROOT/"artifacts/practical-hydrology-p1/probe.json").read_text())["found"]
    cid, w1, water, _, _ = import_snapshots(db, 42, 63_710_000, 3982)
    initialize_reconciliation(db, cid, cutover_minute=0)
    initialize_practical_hydrology(db, cid, PracticalConfig.model_validate(proof["config"]))
    evidence = prepare_natural_passage(db, cid, proof)
    prepare_water_domain(db, cid, evidence.node)
    return cid, w1, water, proof, evidence


def allocation_request(db, cid, proof, evidence, operation="allocate"):
    q = proof["allocation"]["vertex_quota_liters"]
    amount = q[proof["source_vertex"]]+q[proof["target_vertex"]]
    return RevisionRequest(operation_id=operation, logical_minute=0,
        expected_heads={str(evidence.node): get_water_domain(db, cid, evidence.node)["head_id"]},
        transfers=[TransferIntent(transfer_id=operation, source_node=evidence.node, target_node=evidence.node,
            source_account="w1:surface", target_account=POOL, amount_liters=amount, evidence_keys=[evidence.evidence_key])])


def flow_request(db, cid, proof, evidence, operation="flow", amount=None):
    return RevisionRequest(operation_id=operation, logical_minute=proof["config"]["episode_minutes"],
        expected_heads={str(evidence.node): get_water_domain(db, cid, evidence.node)["head_id"]},
        transfers=[TransferIntent(transfer_id=operation, source_node=evidence.node, target_node=evidence.node,
            source_account=evidence.baseline["source_account"], target_account=evidence.baseline["target_account"],
            amount_liters=proof["suggested_transfer_liters"] if amount is None else amount, evidence_keys=[evidence.evidence_key])])


def test_real_positive_transfer_conserves_parent_and_normalized_children(db_session):
    cid, w1, water, proof, evidence = prepare(db_session)
    old_hash = checksum(w1.plan)
    before = get_water_domain(db_session, cid, evidence.node)
    allocated = reconcile(db_session, cid, allocation_request(db_session, cid, proof, evidence))
    assert allocated.payload["local_reconciliation"]["parent_debit_liters"] == 121
    moved = reconcile(db_session, cid, flow_request(db_session, cid, proof, evidence))
    assert moved.payload["local_reconciliation"]["delivered_liters"] == 19
    assert moved.payload["local_reconciliation"]["wetting_liters"] == 11
    assert get_local_account(db_session, cid, evidence.baseline["source_account"])["liters"] == 31
    assert get_local_account(db_session, cid, evidence.baseline["target_account"])["liters"] == 79
    assert get_local_account(db_session, cid, evidence.baseline["wetting_account"])["liters"] == 11
    after = get_water_domain(db_session, cid, evidence.node)
    assert sum(before["state"]["accounts"].values()) == sum(after["state"]["accounts"].values())
    assert after["state"]["accounts"][POOL] == 121
    assert checksum(w1.plan) == old_hash and evidence.node not in dict(water.manifest)


def test_no_double_claim_no_duplicate_episode_and_idempotent_replay(db_session):
    cid, _, _, proof, evidence = prepare(db_session)
    req = allocation_request(db_session, cid, proof, evidence)
    original = reconcile(db_session, cid, req)
    assert reconcile(db_session, cid, req).revision_id == original.revision_id
    with pytest.raises(ValueError, match="not-yet-localized"):
        reconcile(db_session, cid, allocation_request(db_session, cid, proof, evidence, "claim-again"))
    flow = flow_request(db_session, cid, proof, evidence)
    result = reconcile(db_session, cid, flow)
    assert reconcile(db_session, cid, flow).revision_id == result.revision_id
    with pytest.raises(ValueError, match="overlaps|already used"):
        reconcile(db_session, cid, flow_request(db_session, cid, proof, evidence, "reuse-window"))
    assert db_session.query(GenesisPracticalCapacityUse).count() == 1


def test_excess_volume_retained_without_invented_inundation(db_session):
    cid, _, _, proof, evidence = prepare(db_session)
    reconcile(db_session, cid, allocation_request(db_session, cid, proof, evidence))
    with pytest.raises(ValueError, match="reserve|containment|capacity"):
        reconcile(db_session, cid, flow_request(db_session, cid, proof, evidence, amount=10**9))
    assert get_local_account(db_session, cid, evidence.baseline["source_account"])["liters"] == 61
    assert db_session.query(GenesisWaterRevision).count() == 1
    assert db_session.query(GenesisPracticalCapacityUse).count() == 0


def test_geometry_event_blocks_future_flow_without_erasing_history(db_session):
    cid, _, _, proof, evidence = prepare(db_session)
    allocated = reconcile(db_session, cid, allocation_request(db_session, cid, proof, evidence))
    flow = flow_request(db_session, cid, proof, evidence)
    g1 = db_session.get(GenesisHydroGeometryEvidence, (cid, evidence.baseline["g1_request_id"]))
    g1.changes = {"events": [{"id": "new-landslide", "logical_minute": 1}]}
    with pytest.raises(ValueError, match="invalidated"):
        reconcile(db_session, cid, flow)
    assert get_revision(db_session, cid, allocated.revision_id)["payload"]["local_reconciliation"]["child_credit_liters"] == 121
    assert get_local_account(db_session, cid, evidence.baseline["source_account"])["liters"] == 61


def test_reopen_without_height_regeneration_and_rollback(db_session, monkeypatch):
    cid, _, _, proof, evidence = prepare(db_session)
    reconcile(db_session, cid, allocation_request(db_session, cid, proof, evidence))
    flow = flow_request(db_session, cid, proof, evidence)
    target = evidence.baseline["target_account"]
    db_session.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError("Returning to a saved P1 proof must not regenerate terrain")
    monkeypatch.setattr("app.game.world.genesis.terrain.field.TerrainSampler.sample", forbidden)
    with Session(db_session.get_bind()) as reopened:
        saved = reconcile(reopened, cid, flow)
        rid = saved.revision_id
        reopened.rollback()
    with Session(db_session.get_bind()) as reopened:
        assert reopened.get(GenesisWaterRevision, (cid, rid)) is None
        assert get_local_account(reopened, cid, target)["liters"] == 60
        result = reconcile(reopened, cid, flow)
        rid = result.revision_id
        reopened.commit()
    with Session(db_session.get_bind()) as reopened:
        assert get_revision(reopened, cid, rid)["payload"]["local_reconciliation"]["delivered_liters"] == 19
        assert get_local_account(reopened, cid, target)["liters"] == 79


def test_no_implicit_activation_on_existing_w2_domains(db_session):
    cid, _, _, _, _ = import_snapshots(db_session, 42, 63_710_000, 3982)
    initialize_reconciliation(db_session, cid, cutover_minute=0)
    prepare_water_domain(db_session, cid, 3982)
    with pytest.raises(ValueError, match="new W2 authority"):
        initialize_practical_hydrology(db_session, cid)


def test_atomic_failure_after_parent_update_rolls_back_children(db_session):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    cid, _, _, proof, evidence = prepare(db_session)
    allocated = reconcile(db_session, cid, allocation_request(db_session, cid, proof, evidence))
    flow = flow_request(db_session, cid, proof, evidence)
    db_session.execute(text("CREATE TRIGGER fixture_p1_failure BEFORE INSERT ON genesis_practical_capacity_use BEGIN SELECT RAISE(ABORT,'synthetic child-account commit failure'); END"))
    with pytest.raises(IntegrityError):
        reconcile(db_session, cid, flow)
    assert get_water_domain(db_session, cid, evidence.node)["head_id"] == allocated.revision_id
    assert get_local_account(db_session, cid, evidence.baseline["source_account"])["liters"] == 61
    assert get_local_account(db_session, cid, evidence.baseline["target_account"])["liters"] == 60
    assert db_session.query(GenesisLocalWaterAccount).count() == 2
    assert db_session.query(GenesisPracticalCapacityUse).count() == 0


def test_two_sessions_cannot_spend_the_same_real_parcel(tmp_path):
    from sqlalchemy import create_engine, event
    from app.db.base import Base
    from app.db.database import enable_sqlite_foreign_keys
    from app.db.models.world_water_reconciliation import GenesisWaterReconciliationEvidence
    engine = create_engine(f"sqlite:///{(tmp_path/'p1-concurrent.db').as_posix()}")
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid, _, _, proof, evidence = prepare(db)
        reconcile(db, cid, allocation_request(db, cid, proof, evidence))
        key, receiver = evidence.evidence_key, evidence.baseline["target_account"]
        db.commit()
    with Session(engine) as first, Session(engine) as second:
        a = first.get(GenesisWaterReconciliationEvidence, (cid, key))
        b = second.get(GenesisWaterReconciliationEvidence, (cid, key))
        ra, rb = flow_request(first, cid, proof, a, "first-flow"), flow_request(second, cid, proof, b, "second-flow")
        reconcile(first, cid, ra)
        first.commit()
        with pytest.raises(ValueError, match="Stale"):
            reconcile(second, cid, rb)
        second.rollback()
    with Session(engine) as db:
        assert get_local_account(db, cid, receiver)["liters"] == 79
        assert db.query(GenesisPracticalCapacityUse).count() == 1
    engine.dispose()


def test_practical_migration_and_scoped_reset(tmp_path, db_session):
    import os
    import sqlite3
    import subprocess
    import sys
    from app.game.world.reset import delete_campaign
    cid, _, _, proof, evidence = prepare(db_session)
    reconcile(db_session, cid, allocation_request(db_session, cid, proof, evidence))
    reconcile(db_session, cid, flow_request(db_session, cid, proof, evidence))
    delete_campaign(db_session, cid)
    assert db_session.query(GenesisLocalWaterAccount).count() == 0
    path = tmp_path/"p1-migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    def migrate(command, target):
        subprocess.run([sys.executable, "-m", "alembic", command, target], cwd=ROOT/"backend", env=env,
                       check=True, capture_output=True, text=True)
    migrate("upgrade", "p24p7k8l9m0n")
    with sqlite3.connect(path) as db:
        before = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        db.execute("INSERT INTO genesis_water_reconciliations(campaign_id,water_version,signature,config,sources,cutover_minute,write_epoch) VALUES ('old',2,'s','{}','{\"sentinel\":1}',0,0)")
    migrate("upgrade", "q25q8l9m0n1o")
    with sqlite3.connect(path) as db:
        after = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert all(after[k] == v for k, v in before.items())
        assert db.execute("SELECT COUNT(*) FROM genesis_practical_hydrology").fetchone()[0] == 0
    migrate("downgrade", "p24p7k8l9m0n")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT sources FROM genesis_water_reconciliations WHERE campaign_id='old'").fetchone()[0] == '{"sentinel":1}'
