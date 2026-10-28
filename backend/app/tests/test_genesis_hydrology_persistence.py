import json
import os
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_hydrology import GenesisHydrologyPlan, GenesisHydrologySector
from app.db.models.world_spatial import GenesisSphereSector
from app.game.world.genesis.config import WorldConfig
from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.hydrology.sectors import sector_snapshot
from app.game.world.genesis.hydrology.service import (
    clear_plan_cache, get_hydrology_plan, initialize_hydrology, materialize_hydrology_sector, plan_cache_size,
)
from app.game.world.genesis.service import initialize_world, materialize_sector
from app.game.world.genesis.sphere_config import SphereConfig
from app.game.world.genesis.sphere_topology import CellKey, cell_at
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign


@pytest.fixture(autouse=True)
def reset_hydrology_cache():
    clear_plan_cache()
    yield
    clear_plan_cache()


def _world(db, name="H1", seed=42):
    campaign = create_campaign(db, name, world_seed=seed)
    world = initialize_world(db, campaign.id, FormationConfigV4(macro_level=2))
    return campaign, world


def test_h1_is_explicit_v4_only_and_cannot_reconfigure(db_session):
    for config in (WorldConfig(), SphereConfig(), FormationConfig(macro_level=2)):
        campaign = create_campaign(db_session, "Legacy", world_seed=42)
        initialize_world(db_session, campaign.id, config)
        with pytest.raises(ValueError):
            initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
    campaign, _ = _world(db_session)
    with pytest.raises(ValueError):
        get_hydrology_plan(db_session, campaign.id)
    first = initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
    assert initialize_hydrology(db_session, campaign.id) is first
    with pytest.raises(ValueError):
        initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=3))
    assert db_session.query(GenesisHydrologySector).count() == db_session.query(GenesisSphereSector).count() == 0


def test_sector_generation_order_reload_changes_and_lazy_cached_plan(db_session, monkeypatch):
    a, world_a = _world(db_session, "A")
    b, _ = _world(db_session, "B")
    for campaign in (a, b):
        initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
    plan = get_hydrology_plan(db_session, a.id)
    g = geometry(plan.config.level)
    source = next(iter(plan.channel_index))
    keys = [cell_at(g.points[source], 13), CellKey(0, 13, 10, 20), CellKey(5, 13, 8191, 2000)]
    baseline_before = json.dumps(world_a.plan, sort_keys=True)
    forward = {key: materialize_hydrology_sector(db_session, a.id, key).baseline for key in keys}
    reverse = {key: materialize_hydrology_sector(db_session, b.id, key).baseline for key in reversed(keys)}
    assert forward == reverse
    sector = materialize_hydrology_sector(db_session, a.id, keys[0])
    sector.changes = {"events": [{"kind": "future_dam_event", "minute": 999}]}
    ids = a.id, b.id
    db_session.commit()
    def forbidden(*args):
        raise AssertionError("Saved hydrology must not globally rebuild")
    monkeypatch.setattr("app.game.world.genesis.hydrology.service.build_hydrology_plan", forbidden)
    with Session(db_session.get_bind()) as reopened:
        row = reopened.get(GenesisHydrologyPlan, ids[0])
        assert "plan" in inspect(row).unloaded
        loaded = get_hydrology_plan(reopened, ids[0])
        assert loaded == plan
        assert "plan" in inspect(row).unloaded  # cache hit did not decode the global JSON
        saved = materialize_hydrology_sector(reopened, ids[0], keys[0])
        assert saved.baseline == forward[keys[0]]
        assert saved.changes["events"][0]["kind"] == "future_dam_event"
        assert json.dumps(reopened.get(GenesisWorld, ids[0]).plan, sort_keys=True) == baseline_before
    clear_plan_cache()
    with Session(db_session.get_bind()) as reopened:
        loaded = get_hydrology_plan(reopened, ids[0])
        assert loaded.to_dict() == plan.to_dict()
        assert initialize_hydrology(reopened, ids[0]).signature == plan.signature
        assert reopened.query(GenesisHydrologySector).count() == 6


def test_existing_sector_does_not_need_global_payload_and_new_query_does_not_solve_again(db_session, monkeypatch):
    campaign, _ = _world(db_session)
    initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
    key = CellKey(0, 13, 10, 20)
    saved = materialize_hydrology_sector(db_session, campaign.id, key)
    def forbidden(*args):
        raise AssertionError("Persisted sector cannot be regenerated")
    monkeypatch.setattr("app.game.world.genesis.hydrology.service.sector_snapshot", forbidden)
    assert materialize_hydrology_sector(db_session, campaign.id, key) is saved
    monkeypatch.setattr("app.game.world.genesis.hydrology.service.sector_snapshot", sector_snapshot)
    monkeypatch.setattr("app.game.world.genesis.hydrology.drainage.solve", forbidden)
    clear_plan_cache()
    assert materialize_hydrology_sector(db_session, campaign.id, CellKey(0, 13, 11, 20)).baseline


def test_cache_is_limited_and_rollback_cannot_create_phantom_hydrology(db_session):
    worlds = [_world(db_session, f"Cache {i}", seed=i)[0] for i in range(3)]
    for campaign in worlds:
        initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
    assert plan_cache_size() == 2
    db_session.commit()
    materialize_hydrology_sector(db_session, worlds[0].id, CellKey(0, 13, 0, 0))
    db_session.rollback()
    assert db_session.query(GenesisHydrologySector).count() == 0
    pending, _ = _world(db_session, "Pending", seed=100)
    db_session.commit()
    initialize_hydrology(db_session, pending.id, HydrologyConfig(level=2))
    db_session.rollback()
    with pytest.raises(ValueError):
        get_hydrology_plan(db_session, pending.id)


def test_checksums_versions_and_source_changes_fail_closed(db_session):
    campaign, world = _world(db_session)
    row = initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
    row.hydrology_version = 2
    with pytest.raises(ValueError):
        get_hydrology_plan(db_session, campaign.id)
    row.hydrology_version = 1
    row.plan = {**row.plan, "heights": [0]}
    clear_plan_cache()
    with pytest.raises(ValueError, match="checksum"):
        get_hydrology_plan(db_session, campaign.id)
    world.plan = {**world.plan, "signature": "changed_source"}
    with pytest.raises(ValueError):
        get_hydrology_plan(db_session, campaign.id)


def test_payload_cannot_override_pinned_hydrology_header(db_session):
    from app.game.world.genesis.hydrology.plan import signature
    from app.game.world.genesis.hydrology.service import payload_checksum
    campaign, _ = _world(db_session)
    row = initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
    config = HydrologyConfig(level=2, channel_min_area_ppm=250)
    payload = {**row.plan, "config": config.model_dump(), "signature": signature(row.source_signature, config)}
    row.plan, row.payload_checksum = payload, payload_checksum(payload)
    clear_plan_cache()
    with pytest.raises(ValueError, match="pinned header"):
        get_hydrology_plan(db_session, campaign.id)


def test_delete_is_dependency_safe_and_campaign_scoped(db_session):
    a, _ = _world(db_session, "Delete")
    b, _ = _world(db_session, "Keep")
    for campaign in (a, b):
        initialize_hydrology(db_session, campaign.id, HydrologyConfig(level=2))
        materialize_hydrology_sector(db_session, campaign.id, CellKey(0, 13, 10, 20))
    assert delete_campaign(db_session, a.id)
    assert db_session.query(GenesisHydrologyPlan).one().campaign_id == b.id
    assert db_session.query(GenesisHydrologySector).one().campaign_id == b.id


def test_additive_hydrology_migration_preserves_legacy_rows_and_runtime_contract(tmp_path):
    from sqlalchemy import create_engine, event
    from app.db.database import enable_sqlite_foreign_keys
    path = tmp_path/"hydrology_upgrade.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    def migrate(command, target):
        subprocess.run([sys.executable, "-m", "alembic", command, target], env=env,
                       check=True, capture_output=True, text=True)
    migrate("upgrade", "i17i1d2e3f4g")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO campaigns (id,name,world_seed,created_at) VALUES ('legacy','Keep',42,'2026-10-25')")
        before = connection.execute("SELECT * FROM campaigns").fetchall()
    migrate("upgrade", "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM campaigns").fetchall() == before
        assert connection.execute("SELECT count(*) FROM genesis_hydrology_plans").fetchone() == (0,)
    engine = create_engine(env["DATABASE_URL"])
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    with Session(engine) as session:
        campaign, _ = _world(session, "Migrated")
        initialize_hydrology(session, campaign.id, HydrologyConfig(level=2))
        materialize_hydrology_sector(session, campaign.id, CellKey(0, 13, 0, 0))
        session.commit()
        clear_plan_cache()
        assert get_hydrology_plan(session, campaign.id).config.hydrology_version == 1
        assert delete_campaign(session, campaign.id)
        session.commit()
    engine.dispose()
    migrate("downgrade", "i17i1d2e3f4g")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM campaigns").fetchall() == before
