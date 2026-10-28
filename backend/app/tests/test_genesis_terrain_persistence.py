import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from app.db.models.world_terrain import GenesisTerrainPlan, GenesisTerrainTile
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.terrain.address import TerrainTile
from app.game.world.genesis.terrain.config import TerrainConfig
from app.game.world.genesis.terrain.service import (initialize_terrain, get_terrain_sampler,
    materialize_terrain_tile, query_altitude, clear_terrain_cache, terrain_cache_size)
from app.game.world.seed import create_campaign
from app.game.world.reset import delete_campaign


@pytest.fixture(autouse=True)
def cache():
    clear_terrain_cache()
    yield
    clear_terrain_cache()


def world(db, name="T1"):
    campaign = create_campaign(db, name, world_seed=42)
    initialize_world(db, campaign.id, FormationConfigV4(macro_level=2))
    return campaign


def test_opt_in_no_conversion_or_materialization(db_session):
    campaign = world(db_session)
    with pytest.raises(ValueError, match="explicitly"):
        get_terrain_sampler(db_session, campaign.id)
    row = initialize_terrain(db_session, campaign.id)
    assert initialize_terrain(db_session, campaign.id) is row
    assert db_session.query(GenesisTerrainTile).count() == 0
    with pytest.raises(ValueError, match="reconfigure"):
        initialize_terrain(db_session, campaign.id, TerrainConfig(relief_scale_ppm=0))
    legacy = create_campaign(db_session, "legacy", world_seed=42)
    initialize_world(db_session, legacy.id)
    with pytest.raises(ValueError, match="legacy"):
        initialize_terrain(db_session, legacy.id)


def test_saved_terrain_reload_without_generation_and_event_retention(db_session, monkeypatch):
    campaign = world(db_session)
    initialize_terrain(db_session, campaign.id)
    tile = TerrainTile(0, 17, 100, 200)
    row = materialize_terrain_tile(db_session, campaign.id, tile)
    baseline = json.loads(json.dumps(row.baseline))
    point = tile.point(4, 7, 16)
    z = query_altitude(db_session, campaign.id, point)["height_mm"]
    row.changes = {"events": [{"id": "dig-1", "kind": "future_excavation", "delta_mm": -1000}]}
    campaign_id = campaign.id
    db_session.commit()
    clear_terrain_cache()
    def forbidden(*args, **kwargs):
        raise AssertionError("Saved terrain must not rebuild")
    monkeypatch.setattr("app.game.world.genesis.terrain.service.prepare_patch", forbidden)
    monkeypatch.setattr("app.game.world.genesis.terrain.field.TerrainSampler.sample", forbidden)
    with Session(db_session.get_bind()) as reopened:
        saved = reopened.get(GenesisTerrainTile, (campaign_id, *vars(tile).values()))
        assert "baseline" in inspect(saved).unloaded
        assert materialize_terrain_tile(reopened, campaign_id, tile).baseline == baseline
        assert saved.changes["events"][0]["id"] == "dig-1"
        with pytest.raises(ValueError, match="event-aware"):
            query_altitude(reopened, campaign_id, point)
        assert query_altitude(reopened, campaign_id, point, baseline_only=True)["height_mm"] == z


def test_seam_events_and_lod_conflicts_fail_closed(db_session):
    campaign = world(db_session)
    initialize_terrain(db_session, campaign.id)
    # Shared +X/+Y face boundary, query ownership belongs to +X.
    tile = TerrainTile(2, 17, 0, 50000)
    row = materialize_terrain_tile(db_session, campaign.id, tile)
    point = tile.point(0, 8, 16)
    assert query_altitude(db_session, campaign.id, point)["height_mm"] == row.baseline["height_mm"][8][0]
    row.changes = {"events": [{"id": "landslide"}]}
    with pytest.raises(ValueError, match="event-aware"):
        query_altitude(db_session, campaign.id, point)
    # No silent interpolation/rebuild after storage corruption.
    row.changes = {}
    row.baseline_checksum = "broken"
    with pytest.raises(ValueError, match="checksum"):
        materialize_terrain_tile(db_session, campaign.id, tile)


def test_source_header_and_version_checks(db_session):
    campaign = world(db_session)
    row = initialize_terrain(db_session, campaign.id)
    get_terrain_sampler(db_session, campaign.id)
    row.terrain_version = 2
    with pytest.raises(ValueError, match="version"):
        get_terrain_sampler(db_session, campaign.id)
    row.terrain_version = 1
    row.plan = {**row.plan, "base_level": 0}
    with pytest.raises(ValueError, match="descriptor"):
        get_terrain_sampler(db_session, campaign.id)


def test_preexisting_physical_territory_is_not_reinterpreted(db_session):
    from app.game.world.genesis.service import materialize_sector
    from app.game.world.genesis.sphere_topology import CellKey
    campaign = world(db_session)
    old = materialize_sector(db_session, campaign.id, CellKey(0, 13, 10, 10))
    old.changes = {"events": [{"kind": "old_excavation"}]}
    baseline = json.dumps(old.baseline, sort_keys=True)
    with pytest.raises(ValueError, match="migration"):
        initialize_terrain(db_session, campaign.id)
    assert db_session.get(GenesisTerrainPlan, campaign.id) is None
    assert json.dumps(old.baseline, sort_keys=True) == baseline
    assert old.changes["events"][0]["kind"] == "old_excavation"


def test_rollback_no_phantom_tiles_cache_bound_and_scoped_reset(db_session):
    campaigns = [world(db_session, str(i)) for i in range(3)]
    for campaign in campaigns:
        initialize_terrain(db_session, campaign.id)
        get_terrain_sampler(db_session, campaign.id)
    assert terrain_cache_size() <= 2
    db_session.commit()
    ids = [c.id for c in campaigns]
    tile = TerrainTile(0, 17, 100, 100)
    materialize_terrain_tile(db_session, ids[0], tile)
    db_session.rollback()
    assert db_session.query(GenesisTerrainTile).count() == 0
    for campaign_id in ids:
        materialize_terrain_tile(db_session, campaign_id, tile)
    delete_campaign(db_session, ids[0])
    assert db_session.get(GenesisTerrainPlan, ids[0]) is None
    assert db_session.query(GenesisTerrainTile).count() == 2


def test_additive_migration_retains_legacy_payload_and_downgrade(tmp_path):
    path = tmp_path/"terrain_migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    cwd = Path(__file__).resolve().parents[2]
    def migrate(command, revision):
        subprocess.run([sys.executable, "-m", "alembic", command, revision], cwd=cwd, env=env,
                       check=True, capture_output=True, text=True)
    migrate("upgrade", "m21m4h5i6j7k")
    with sqlite3.connect(path) as db:
        # Snapshot ALL legacy schemas; additive T1 must not rewrite any of them.
        before = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        db.execute("INSERT INTO genesis_worlds(campaign_id,world_seed,config,plan) VALUES ('old',42,'{}','{\"sentinel\":1}')")
    migrate("upgrade", "n22n5i6j7k8l")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM genesis_terrain_plans").fetchone()[0] == 0
        assert db.execute("SELECT plan FROM genesis_worlds WHERE campaign_id='old'").fetchone()[0] == '{"sentinel":1}'
        after = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert all(after[name] == sql for name, sql in before)
    migrate("downgrade", "m21m4h5i6j7k")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT plan FROM genesis_worlds WHERE campaign_id='old'").fetchone()[0] == '{"sentinel":1}'
