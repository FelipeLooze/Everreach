import json
import os
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.models.world_climate import GenesisClimatePlan, GenesisClimateSector
from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_hydrology import GenesisHydrologyPlan
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.service import (
    clear_climate_cache, climate_cache_size, get_climate_plan, initialize_climate, materialize_climate_sector, query_climate,
)
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.regional_service import initialize_regional_hydrology, materialize_hydrology_region
from app.game.world.genesis.hydrology.service import initialize_hydrology, materialize_hydrology_sector
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.sphere_topology import CellKey, SurfacePoint
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign


@pytest.fixture(autouse=True)
def reset_climate_cache():
    clear_climate_cache()
    yield
    clear_climate_cache()


def world(db, name="C1", seed=42):
    campaign = create_campaign(db, name, world_seed=seed)
    initialize_world(db, campaign.id, FormationConfigV4(macro_level=2))
    initialize_hydrology(db, campaign.id, HydrologyConfig(level=2))
    return campaign


def test_c1_opt_in_config_pinning_and_no_hydrology_or_sector_materialization(db_session):
    old = create_campaign(db_session, "Legacy")
    initialize_world(db_session, old.id)
    with pytest.raises(ValueError):
        initialize_climate(db_session, old.id)
    missing = create_campaign(db_session, "V4 without H1")
    initialize_world(db_session, missing.id, FormationConfigV4(macro_level=2))
    with pytest.raises(ValueError):
        initialize_climate(db_session, missing.id)
    campaign = world(db_session)
    h1 = db_session.get(GenesisHydrologyPlan, campaign.id)
    before = json.dumps(h1.plan, sort_keys=True)
    with pytest.raises(ValueError):
        get_climate_plan(db_session, campaign.id)
    row = initialize_climate(db_session, campaign.id, ClimateConfig(level=3))
    assert initialize_climate(db_session, campaign.id) is row
    assert db_session.query(GenesisClimateSector).count() == 0
    assert json.dumps(h1.plan, sort_keys=True) == before
    with pytest.raises(ValueError):
        initialize_climate(db_session, campaign.id, ClimateConfig(level=4))


def test_order_persistence_changes_deferred_payload_and_no_global_rebuild(db_session, monkeypatch):
    a, b = world(db_session, "A"), world(db_session, "B")
    for campaign in (a, b):
        initialize_climate(db_session, campaign.id, ClimateConfig(level=3))
    keys = [CellKey(0, 13, 123, 456), CellKey(5, 13, 7000, 4000)]
    forward = {k: materialize_climate_sector(db_session, a.id, k).baseline for k in keys}
    reverse = {k: materialize_climate_sector(db_session, b.id, k).baseline for k in reversed(keys)}
    assert forward == reverse
    row = materialize_climate_sector(db_session, a.id, keys[0])
    row.changes = {"events": [{"kind": "future_environment_event", "minute": 1000}]}
    ids = a.id, b.id
    db_session.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError("Returning to C1 must not globally regenerate or requery a saved sector")
    monkeypatch.setattr("app.game.world.genesis.climate.service.build_climate_plan", forbidden)
    monkeypatch.setattr("app.game.world.genesis.climate.service.query_climate", forbidden)
    with Session(db_session.get_bind()) as reopened:
        plan_row = reopened.get(GenesisClimatePlan, ids[0])
        assert "plan" in inspect(plan_row).unloaded
        get_climate_plan(reopened, ids[0])
        assert "plan" in inspect(plan_row).unloaded
        saved = materialize_climate_sector(reopened, ids[0], keys[0])
        assert saved.baseline == forward[keys[0]] and saved.changes["events"][0]["minute"] == 1000
    clear_climate_cache()
    with Session(db_session.get_bind()) as reopened:
        assert get_climate_plan(reopened, ids[0]).signature == get_climate_plan(reopened, ids[1]).signature
        assert reopened.query(GenesisClimateSector).count() == 4


def test_cache_limit_rollback_and_scoped_campaign_deletion(db_session):
    campaigns = [world(db_session, f"C{i}", i) for i in range(3)]
    for campaign in campaigns:
        initialize_climate(db_session, campaign.id, ClimateConfig(level=3))
    assert climate_cache_size() == 2
    db_session.commit()
    materialize_climate_sector(db_session, campaigns[0].id, CellKey(0, 13, 1, 2))
    db_session.rollback()
    assert db_session.query(GenesisClimateSector).count() == 0
    materialize_climate_sector(db_session, campaigns[1].id, CellKey(0, 13, 1, 2))
    assert delete_campaign(db_session, campaigns[0].id)
    assert db_session.query(GenesisClimatePlan).count() == 2
    assert db_session.query(GenesisClimateSector).one().campaign_id == campaigns[1].id
    pending = world(db_session, "Pending", 123)
    db_session.commit()
    initialize_climate(db_session, pending.id, ClimateConfig(level=3))
    db_session.rollback()
    with pytest.raises(ValueError):
        get_climate_plan(db_session, pending.id)


def test_source_versions_and_checksums_fail_without_regeneration(db_session):
    campaign = world(db_session)
    row = initialize_climate(db_session, campaign.id, ClimateConfig(level=3))
    key = CellKey(0, 13, 0, 0)
    saved = materialize_climate_sector(db_session, campaign.id, key)
    saved.baseline = {**saved.baseline, "annual_precipitation_mm": -1}
    with pytest.raises(ValueError, match="refusing regeneration"):
        materialize_climate_sector(db_session, campaign.id, key)
    row.climate_version = 2
    with pytest.raises(ValueError):
        get_climate_plan(db_session, campaign.id)
    row.climate_version = 1
    row.plan = {**row.plan, "heights": [0]}
    clear_climate_cache()
    with pytest.raises(ValueError, match="checksum"):
        get_climate_plan(db_session, campaign.id)
    db_session.get(GenesisHydrologyPlan, campaign.id).payload_checksum = "changed_h1"
    with pytest.raises(ValueError):
        get_climate_plan(db_session, campaign.id)


def test_regional_read_contract_and_sector_level(db_session):
    campaign = world(db_session)
    initialize_climate(db_session, campaign.id, ClimateConfig(level=3))
    point = SurfacePoint(1, 2, 3)
    a = query_climate(db_session, campaign.id, point)
    b = query_climate(db_session, campaign.id, point, regional=False)
    assert a["annual_precipitation_mm"] == b["annual_precipitation_mm"]
    assert a["resolution"] == "regional_v4_altitude_adjustment"
    with pytest.raises(ValueError):
        materialize_climate_sector(db_session, campaign.id, CellKey(0, 12, 1, 1))


def test_additive_c1_migration_preserves_all_existing_sources_and_hr1(tmp_path):
    from sqlalchemy import create_engine, event
    from app.db.database import enable_sqlite_foreign_keys
    path = tmp_path/"climate_upgrade.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    def migrate(command, target):
        subprocess.run([sys.executable, "-m", "alembic", command, target], env=env,
                       check=True, capture_output=True, text=True)
    migrate("upgrade", "k19k2f3g4h5i")
    engine = create_engine(env["DATABASE_URL"])
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    with Session(engine) as session:
        campaign = world(session)
        cid = campaign.id
        materialize_hydrology_sector(session, cid, CellKey(0, 13, 10, 20))
        initialize_regional_hydrology(session, cid)
        materialize_hydrology_region(session, cid, 5)
        session.commit()
    tables = ("campaigns", "genesis_worlds", "genesis_hydrology_plans", "genesis_hydrology_sectors",
              "genesis_hydrology_refinements", "genesis_hydrology_regions")
    def rows():
        with sqlite3.connect(path) as connection:
            return {t: connection.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
    before = rows()
    migrate("upgrade", "head")
    assert rows() == before
    with Session(engine) as session:
        assert session.query(GenesisClimatePlan).count() == 0
        initialize_climate(session, cid, ClimateConfig(level=3))
        materialize_climate_sector(session, cid, CellKey(0, 13, 10, 20))
        session.commit()
        clear_climate_cache()
        assert get_climate_plan(session, cid).config.climate_version == 1
    assert rows() == before
    engine.dispose()
    migrate("downgrade", "k19k2f3g4h5i")
    assert rows() == before
