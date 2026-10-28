from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_water_reconciliation import GenesisWaterRevision, GenesisWaterDomain, GenesisWaterTransfer
from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
from app.game.world.seed import create_campaign
from app.game.world.reset import delete_campaign
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.service import initialize_hydrology
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.regional_service import initialize_regional_hydrology
from app.game.world.genesis.climate.service import initialize_climate
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.water.service import initialize_water_balance
from app.game.world.genesis.terrain.service import initialize_terrain
from app.game.world.genesis.hydro_geometry.service import initialize_geometry, prepare_regional_geometry
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.water_reconciliation.config import RevisionRequest, TransferIntent
from app.game.world.genesis.water_reconciliation.service import (initialize_reconciliation, prepare_water_domain,
    register_geometry_evidence, reconcile, get_revision, get_water_domain)


def world(db, name="W2", manifest_nodes=None):
    c = create_campaign(db, name, world_seed=42)
    initialize_world(db, c.id, FormationConfigV4(macro_level=2))
    initialize_hydrology(db, c.id, HydrologyConfig(level=2))
    initialize_regional_hydrology(db, c.id)
    initialize_climate(db, c.id, ClimateConfigV2(level=3))
    w1 = initialize_water_balance(db, c.id, regional_nodes=manifest_nodes)
    initialize_terrain(db, c.id)
    initialize_geometry(db, c.id)
    return c, w1


def revision(db, cid, operation, minute=0, keys=(), nodes=(5,), transfers=()):
    heads = {str(node): get_water_domain(db, cid, node)["head_id"] for node in nodes}
    return RevisionRequest(operation_id=operation, logical_minute=minute, expected_heads=heads,
                           evidence_keys=list(keys), transfers=list(transfers))


def test_opt_in_opening_once_idempotence_and_history(db_session):
    c, w1 = world(db_session)
    with pytest.raises(ValueError, match="explicitly"):
        prepare_water_domain(db_session, c.id, 5)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    opening = prepare_water_domain(db_session, c.id, 5)
    before = deepcopy(opening.state)
    req = revision(db_session, c.id, "first")
    row = reconcile(db_session, c.id, req)
    assert reconcile(db_session, c.id, req).revision_id == row.revision_id
    assert db_session.query(GenesisWaterRevision).count() == 1
    assert get_water_domain(db_session, c.id, 5)["state"] == before
    second = reconcile(db_session, c.id, revision(db_session, c.id, "second", minute=1))
    assert second.payload["previous_heads"]["5"] == row.revision_id
    assert reconcile(db_session, c.id, req).revision_id == row.revision_id
    changed = RevisionRequest.model_validate({**req.model_dump(), "logical_minute": 1})
    with pytest.raises(ValueError, match="different intent"):
        reconcile(db_session, c.id, changed)
    assert get_revision(db_session, c.id, row.revision_id)["historical"]


def test_new_regional_evidence_does_not_extend_w1_and_remains_pending(db_session):
    c, w1 = world(db_session)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    prepare_water_domain(db_session, c.id, 5)
    before = checksum(w1.plan)
    g1 = prepare_regional_geometry(db_session, c.id, 5)
    evidence = register_geometry_evidence(db_session, c.id, g1.request_id, logical_minute=0)
    state = get_water_domain(db_session, c.id, 5)["state"]
    account = next(iter(state["accounts"]))
    transfer = TransferIntent(transfer_id="pending", source_node=5, target_node=5, source_account=account,
        amount_liters=1, evidence_keys=[evidence.evidence_key])
    result = reconcile(db_session, c.id, revision(db_session, c.id, "with-evidence", keys=[evidence.evidence_key], transfers=[transfer]))
    assert result.payload["transfers"][0]["applied_liters"] == 0
    assert "hydraulic_capacity_not_proved_by_G1_v1" in result.payload["transfers"][0]["reasons"]
    assert checksum(w1.plan) == before and w1.manifest == []
    assert get_water_domain(db_session, c.id, 5)["state"] == state


def test_current_events_do_not_erase_w1_or_past_revision(db_session):
    c, w1 = world(db_session, manifest_nodes=[5])
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    prepare_water_domain(db_session, c.id, 5)
    g1 = prepare_regional_geometry(db_session, c.id, 5)
    evidence = register_geometry_evidence(db_session, c.id, g1.request_id, logical_minute=0)
    old = reconcile(db_session, c.id, revision(db_session, c.id, "before-event", keys=[evidence.evidence_key]))
    digest = old.payload_checksum
    hr = db_session.get(GenesisHydrologyRegion, (c.id, 5))
    hr.changes = {"events": [{"id": "landslide", "logical_minute": 1}]}
    new = reconcile(db_session, c.id, revision(db_session, c.id, "after-event", minute=1, keys=[evidence.evidence_key]))
    assert new.payload["evidence"][evidence.evidence_key]["status"] == "invalidated"
    assert get_revision(db_session, c.id, old.revision_id)["payload"]["logical_minute"] == 0
    assert old.payload_checksum == digest


def test_stale_heads_and_backdated_revisions_rejected(db_session):
    c, _ = world(db_session)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    prepare_water_domain(db_session, c.id, 5)
    old = revision(db_session, c.id, "a", minute=10)
    reconcile(db_session, c.id, old)
    stale = RevisionRequest.model_validate({**old.model_dump(), "operation_id": "b"})
    with pytest.raises(ValueError, match="Stale"):
        reconcile(db_session, c.id, stale)
    with pytest.raises(ValueError, match="backwards"):
        reconcile(db_session, c.id, revision(db_session, c.id, "c", minute=9))
    assert db_session.query(GenesisWaterRevision).count() == 1


def test_reopen_rollback_and_no_solver_or_geometry_regeneration(db_session, monkeypatch):
    c, _ = world(db_session)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    prepare_water_domain(db_session, c.id, 5)
    cid, old_head = c.id, get_water_domain(db_session, c.id, 5)["head_id"]
    db_session.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError("W2 must not replay global W1 or rebuild G1")
    monkeypatch.setattr("app.game.world.genesis.water.plan.solve", forbidden)
    monkeypatch.setattr("app.game.world.genesis.hydro_geometry.service.build_geometry", forbidden)
    with Session(db_session.get_bind()) as reopened:
        result = reconcile(reopened, cid, revision(reopened, cid, "rollback"))
        rid = result.revision_id
        reopened.rollback()
    with Session(db_session.get_bind()) as reopened:
        assert get_water_domain(reopened, cid, 5)["head_id"] == old_head
        assert reopened.get(GenesisWaterRevision, (cid, rid)) is None


def test_more_than_32_domains_are_lazy_and_no_w1_manifest_change(db_session):
    c, w1 = world(db_session)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    for node in range(33):
        prepare_water_domain(db_session, c.id, node)
    assert db_session.query(GenesisWaterDomain).count() == 33
    assert w1.manifest == []


def test_scoped_reset_and_migration(tmp_path, db_session):
    a, _ = world(db_session, "A")
    b, _ = world(db_session, "B")
    for c in (a, b):
        initialize_reconciliation(db_session, c.id, cutover_minute=0)
        prepare_water_domain(db_session, c.id, 5)
        reconcile(db_session, c.id, revision(db_session, c.id, "held"))
    delete_campaign(db_session, a.id)
    assert db_session.query(GenesisWaterDomain).count() == db_session.query(GenesisWaterRevision).count() == 1
    path = tmp_path/"w2_upgrade.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    cwd = Path(__file__).resolve().parents[2]
    def migrate(command, target):
        subprocess.run([sys.executable, "-m", "alembic", command, target], cwd=cwd, env=env, check=True, capture_output=True, text=True)
    migrate("upgrade", "o23o6j7k8l9m")
    with sqlite3.connect(path) as db:
        before = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        db.execute("INSERT INTO genesis_water_plans(campaign_id,water_version,signature,config,hydrology_signature,hydrology_checksum,climate_signature,climate_checksum,hr_signature,manifest,payload_checksum,plan) VALUES ('old',1,'s','{}','h','hh','c','cc','r','[]','x','{\"sentinel\":9}')")
    migrate("upgrade", "p24p7k8l9m0n")
    with sqlite3.connect(path) as db:
        after = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert all(after[k] == v for k, v in before.items())
        assert db.execute("SELECT COUNT(*) FROM genesis_water_reconciliations").fetchone()[0] == 0
        assert db.execute("SELECT plan FROM genesis_water_plans WHERE campaign_id='old'").fetchone()[0] == '{"sentinel":9}'
    migrate("downgrade", "o23o6j7k8l9m")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT plan FROM genesis_water_plans WHERE campaign_id='old'").fetchone()[0] == '{"sentinel":9}'


def test_preparation_order_does_not_change_reconciliation_result(db_session):
    campaigns = [world(db_session, name)[0] for name in ("Order A", "Order B")]
    results = []
    for i, c in enumerate(campaigns):
        initialize_reconciliation(db_session, c.id, cutover_minute=0)
        prepare_water_domain(db_session, c.id, 5)
        keys = []
        for node in ([5, 6] if i == 0 else [6, 5]):
            g1 = prepare_regional_geometry(db_session, c.id, node)
            keys.append(register_geometry_evidence(db_session, c.id, g1.request_id, logical_minute=i).evidence_key)
        results.append(reconcile(db_session, c.id, revision(db_session, c.id, "same-state", minute=2, keys=keys)).payload)
    assert results[0] == results[1]


def test_synthetic_positive_transaction_deduplicates_and_reopens(db_session, monkeypatch):
    # Controlled persistence fixture, NOT a claim that any real G1 has capacity.
    from app.tests.test_genesis_water_reconciliation import stock, admitted
    import app.game.world.genesis.water_reconciliation.service as service
    c, _ = world(db_session)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    monkeypatch.setattr(service, "opening_state", lambda water, node: stock(100 if node == 5 else 0))
    monkeypatch.setattr(service, "assess_transfer", lambda *args, **kwargs: admitted(100))
    for node in (5, 6):
        prepare_water_domain(db_session, c.id, node)
    move = TransferIntent(transfer_id="fixture-positive", source_node=5, target_node=6,
        source_account="at:inlet", target_account="at:inlet", amount_liters=40)
    req = revision(db_session, c.id, "synthetic-positive", nodes=(5, 6), transfers=[move])
    record = reconcile(db_session, c.id, req)
    assert record.payload["transfers"][0]["applied_liters"] == 40
    assert reconcile(db_session, c.id, req).revision_id == record.revision_id
    assert db_session.query(GenesisWaterTransfer).count() == 1
    with pytest.raises(ValueError, match="already applied"):
        reconcile(db_session, c.id, revision(db_session, c.id, "duplicate-transfer", nodes=(5, 6), transfers=[move]))
    cid, rid = c.id, record.revision_id
    db_session.commit()
    with Session(db_session.get_bind()) as reopened:
        assert get_water_domain(reopened, cid, 5)["state"]["accounts"]["at:inlet"] == 60
        assert get_water_domain(reopened, cid, 6)["state"]["accounts"]["at:inlet"] == 40
        assert get_revision(reopened, cid, rid)["payload"]["budgets"]["5"]["residual_liters"] == 0


def test_two_sessions_reject_stale_predecessor(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path/'concurrent.db').as_posix()}")
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        c, _ = world(db)
        cid = c.id
        initialize_reconciliation(db, cid, cutover_minute=0)
        prepare_water_domain(db, cid, 5)
        db.commit()
    with Session(engine) as first, Session(engine) as second:
        a = revision(first, cid, "session-a")
        b = revision(second, cid, "session-b")
        winner = reconcile(first, cid, a)
        rid = winner.revision_id
        first.commit()
        with pytest.raises(ValueError, match="Stale"):
            reconcile(second, cid, b)
        second.rollback()
    with Session(engine) as db:
        assert db.query(GenesisWaterRevision).count() == 1
        assert get_water_domain(db, cid, 5)["head_id"] == rid
    engine.dispose()


def test_single_authority_and_revision_budget_failure_are_conservative(db_session):
    from app.game.world.genesis.water_reconciliation.service import query_water_state
    from app.game.world.genesis.water_reconciliation.config import ReconciliationConfig
    c, _ = world(db_session)
    initialize_reconciliation(db_session, c.id, ReconciliationConfig(max_payload_bytes=4096), cutover_minute=0)
    old = query_water_state(db_session, c.id, 5)
    assert old["prepared"] is False
    assert db_session.query(GenesisWaterDomain).count() == 0
    prepare_water_domain(db_session, c.id, 5)
    assert query_water_state(db_session, c.id, 5)["state"] == old["state"]
    keys = []
    for node in (5, 6, 7, 8):
        g1 = prepare_regional_geometry(db_session, c.id, node)
        keys.append(register_geometry_evidence(db_session, c.id, g1.request_id, logical_minute=0).evidence_key)
    req = revision(db_session, c.id, "too-large", keys=keys)
    with pytest.raises(ValueError, match="persistence budget"):
        reconcile(db_session, c.id, req)
    assert get_water_domain(db_session, c.id, 5)["head_id"] == old["head_id"]
    assert db_session.query(GenesisWaterRevision).count() == 0


def test_pending_revision_matches_across_processes(db_session):
    c, _ = world(db_session)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    prepare_water_domain(db_session, c.id, 5)
    result = reconcile(db_session, c.id, revision(db_session, c.id, "golden"))
    code = """from app.tests.test_genesis_water_reconciliation_persistence import *
engine=create_engine('sqlite:///:memory:')
event.listen(engine,'connect',enable_sqlite_foreign_keys)
Base.metadata.create_all(engine)
with Session(engine) as db:
    c,_=world(db)
    initialize_reconciliation(db,c.id,cutover_minute=0)
    prepare_water_domain(db,c.id,5)
    r=reconcile(db,c.id,revision(db,c.id,'golden'))
    print(r.payload_checksum)
engine.dispose()"""
    got = subprocess.check_output([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2], text=True).strip().splitlines()[-1]
    assert got == result.payload_checksum
    assert got == "d83edb426f978a7b1fbac6fe954575a37efa62517eeda15a70b6f545664d15b9"


def test_registry_can_grow_beyond_w1_manifest_budget_without_water_domains(db_session):
    from app.db.models.world_water_reconciliation import GenesisWaterReconciliationEvidence
    from app.game.world.genesis.hydro_geometry.service import materialize_geometry
    from app.game.world.genesis.hydro_geometry.config import GeometryRequest, Anchor
    from app.game.world.genesis.terrain.address import tile_at, TerrainTile
    from app.game.world.genesis.sphere_topology import SurfacePoint
    c, w1 = world(db_session)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    tile = tile_at(SurfacePoint(3, 2, 1), 20)
    for i in range(33):
        local = TerrainTile(tile.face, tile.level, tile.x+i, tile.y)
        req = GeometryRequest(tile=list(vars(local).values()), grid_intervals=4, anchors=[
            Anchor(id="entry", point=list(local.point(0, 2, 4).xyz), role="ingress"),
            Anchor(id="exit", point=list(local.point(4, 2, 4).xyz), role="outlet")])
        saved = materialize_geometry(db_session, c.id, req)
        register_geometry_evidence(db_session, c.id, saved.request_id, logical_minute=0)
    assert db_session.query(GenesisWaterReconciliationEvidence).count() == 33
    assert db_session.query(GenesisWaterDomain).count() == 0
    assert w1.manifest == []


def test_mid_batch_storage_failure_rolls_back_all_domains(db_session, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.tests.test_genesis_water_reconciliation import stock, admitted
    import app.game.world.genesis.water_reconciliation.service as service
    c, _ = world(db_session)
    initialize_reconciliation(db_session, c.id, cutover_minute=0)
    monkeypatch.setattr(service, "opening_state", lambda water, node: stock(100 if node == 5 else 0))
    monkeypatch.setattr(service, "assess_transfer", lambda *args, **kwargs: admitted(100))
    for node in (5, 6):
        prepare_water_domain(db_session, c.id, node)
    heads = {node: get_water_domain(db_session, c.id, node)["head_id"] for node in (5, 6)}
    db_session.execute(text("CREATE TRIGGER fixture_w2_abort BEFORE UPDATE ON genesis_water_domains WHEN NEW.node=6 BEGIN SELECT RAISE(ABORT,'synthetic mid-batch failure'); END"))
    move = TransferIntent(transfer_id="synthetic-fail", source_node=5, target_node=6,
        source_account="at:inlet", target_account="at:inlet", amount_liters=40)
    with pytest.raises(IntegrityError):
        reconcile(db_session, c.id, revision(db_session, c.id, "mid-batch", nodes=(5, 6), transfers=[move]))
    assert db_session.query(GenesisWaterRevision).count() == 0
    assert db_session.query(GenesisWaterTransfer).count() == 0
    for node in (5, 6):
        assert get_water_domain(db_session, c.id, node)["head_id"] == heads[node]
