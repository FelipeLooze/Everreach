import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.models.world_climate import GenesisClimatePlan, GenesisClimateSector
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.service import (
    clear_climate_cache, climate_cache_size, get_climate_plan, initialize_climate, materialize_climate_sector,
)
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.service import initialize_hydrology, payload_checksum
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.sphere_topology import CellKey
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign


@pytest.fixture(autouse=True)
def clear_cache():
    clear_climate_cache()
    yield
    clear_climate_cache()


def world(db, name, version, seed=42):
    campaign = create_campaign(db, name, world_seed=seed)
    initialize_world(db, campaign.id, FormationConfigV4(macro_level=2))
    initialize_hydrology(db, campaign.id, HydrologyConfig(level=2))
    initialize_climate(db, campaign.id, (ClimateConfigV2 if version == 2 else ClimateConfig)(level=3))
    return campaign


def test_c2_requires_explicit_configuration_and_cannot_convert_c1(db_session):
    old = world(db_session, "C1", 1)
    c1 = db_session.get(GenesisClimatePlan, old.id)
    before = json.dumps(c1.plan, sort_keys=True)
    with pytest.raises(ValueError, match="reconfigure"):
        initialize_climate(db_session, old.id, ClimateConfigV2(level=3))
    assert initialize_climate(db_session, old.id) is c1
    assert c1.climate_version == 1 and json.dumps(c1.plan, sort_keys=True) == before
    new = world(db_session, "C2", 2)
    c2 = get_climate_plan(db_session, new.id)
    assert c2.config.climate_version == 2
    assert c2.source_signature == c1.source_signature and c2.signature != c1.signature
    assert db_session.query(GenesisClimateSector).count() == 0


def test_c1_c2_snapshots_order_changes_and_reload_without_solver(db_session, monkeypatch):
    old = world(db_session, "Preserved C1", 1)
    a, b = world(db_session, "C2 A", 2), world(db_session, "C2 B", 2)
    keys = [CellKey(0, 13, 200, 300), CellKey(4, 13, 4000, 2000)]
    old_row = materialize_climate_sector(db_session, old.id, keys[0])
    old_before = json.dumps(old_row.baseline, sort_keys=True)
    forward = {key: materialize_climate_sector(db_session, a.id, key).baseline for key in keys}
    reverse = {key: materialize_climate_sector(db_session, b.id, key).baseline for key in reversed(keys)}
    assert forward == reverse
    row = materialize_climate_sector(db_session, a.id, keys[0])
    row.changes = {"events": [{"kind": "future_local_event", "time": 999}]}
    ids = old.id, a.id, b.id
    db_session.commit()
    clear_climate_cache()
    def forbidden(*args, **kwargs):
        raise AssertionError("A saved climate version must not regenerate")
    monkeypatch.setattr("app.game.world.genesis.climate.service.build_climate_plan", forbidden)
    monkeypatch.setattr("app.game.world.genesis.climate.plan._solve_climate", forbidden)
    with Session(db_session.get_bind()) as reopened:
        assert get_climate_plan(reopened, ids[0]).config.climate_version == 1
        assert get_climate_plan(reopened, ids[1]).config.climate_version == 2
        saved = materialize_climate_sector(reopened, ids[1], keys[0])
        assert saved.baseline == forward[keys[0]] and saved.changes["events"][0]["time"] == 999
        assert json.dumps(materialize_climate_sector(reopened, ids[0], keys[0]).baseline, sort_keys=True) == old_before
        assert climate_cache_size() <= 2


def test_mixed_version_cache_rollback_and_scoped_deletion(db_session):
    a, b = world(db_session, "C1", 1), world(db_session, "C2", 2)
    assert climate_cache_size() == 2
    db_session.commit()
    materialize_climate_sector(db_session, b.id, CellKey(0, 13, 1, 1))
    db_session.rollback()
    assert db_session.query(GenesisClimateSector).count() == 0
    materialize_climate_sector(db_session, a.id, CellKey(0, 13, 1, 1))
    assert delete_campaign(db_session, b.id)
    assert db_session.query(GenesisClimatePlan).one().climate_version == 1
    assert db_session.query(GenesisClimateSector).one().campaign_id == a.id


def test_c2_pinned_header_and_payload_version_mismatch_fail_closed(db_session):
    campaign = world(db_session, "C2", 2)
    row = db_session.get(GenesisClimatePlan, campaign.id)
    row.climate_version = 1
    with pytest.raises(ValueError):
        get_climate_plan(db_session, campaign.id)
    row.climate_version = 2
    row.plan = {**row.plan, "kind": "climate_c1"}
    row.payload_checksum = payload_checksum(row.plan)
    clear_climate_cache()
    with pytest.raises(ValueError, match="provenance"):
        get_climate_plan(db_session, campaign.id)


def test_existing_alembic_schema_reads_both_versions_without_migration(tmp_path):
    from app.db.database import enable_sqlite_foreign_keys
    path = tmp_path/"climate_versions.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "l20l3g4h5i6j"], env=env,
                   check=True, capture_output=True, text=True)
    engine = create_engine(env["DATABASE_URL"])
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    with Session(engine) as session:
        old = world(session, "C1", 1)
        key = CellKey(0, 13, 100, 100)
        snapshot = materialize_climate_sector(session, old.id, key)
        snapshot.changes = {"preserve": "legacy event"}
        before = json.dumps([session.get(GenesisClimatePlan, old.id).plan, snapshot.baseline, snapshot.changes], sort_keys=True)
        new = world(session, "C2", 2)
        materialize_climate_sector(session, new.id, key)
        ids = old.id, new.id
        session.commit()
    clear_climate_cache()
    with Session(engine) as session:
        a = get_climate_plan(session, ids[0])
        b = get_climate_plan(session, ids[1])
        snapshot = materialize_climate_sector(session, ids[0], key)
        after = json.dumps([session.get(GenesisClimatePlan, ids[0]).plan, snapshot.baseline, snapshot.changes], sort_keys=True)
        assert before == after and (a.config.climate_version, b.config.climate_version) == (1, 2)
    engine.dispose()
