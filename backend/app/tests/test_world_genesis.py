import json
import os
import subprocess
import sys

import pytest
from sqlalchemy.orm import Session

from app.db.models.world_genesis import GenesisSector, GenesisWorld
from app.game.world.genesis.config import WorldConfig
from app.game.world.genesis.coordinates import (
    SectorKey, canonical_sector, nearby_sectors, sector_at,
)
from app.game.world.genesis.geography import elevation_at, generate_sector
from app.game.world.genesis.randomness import coordinate_seed
from app.game.world.genesis.service import initialize_world, materialize_sector
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign


CONFIG = WorldConfig()


def test_replay_across_process_hash_seeds():
    source = ("import json; from app.game.world.genesis.geography import generate_sector; "
              "from app.game.world.genesis.config import WorldConfig; "
              "from app.game.world.genesis.coordinates import SectorKey; "
              "print(json.dumps(generate_sector(123, WorldConfig(), SectorKey(31,32)), sort_keys=True))")
    outputs = [subprocess.check_output([sys.executable, "-c", source],
               env={**os.environ, "PYTHONHASHSEED": value}, text=True)
               for value in ("1", "982")]
    assert outputs[0] == outputs[1]
    assert json.loads(outputs[0]) == generate_sector(123, CONFIG, SectorKey(31, 32))


def test_entropy_is_addressable_and_subsystem_independent():
    expected = coordinate_seed(44, 1, "relief", 3, 7)
    assert expected == 8291085450287003950  # v1 replay contract
    for i in range(100):
        coordinate_seed(44, 1, "climate", i, 7)
    assert coordinate_seed(44, 1, "relief", 3, 7) == expected
    assert len({expected, coordinate_seed(45, 1, "relief", 3, 7),
                coordinate_seed(44, 2, "relief", 3, 7),
                coordinate_seed(44, 1, "climate", 3, 7)}) == 4


@pytest.mark.parametrize("key", [SectorKey(31, 32), SectorKey(0, 0), SectorKey(2559, 1278)])
def test_shared_edges_and_global_sampling(key):
    a = generate_sector(42, CONFIG, key)["elevation_m"]
    east = generate_sector(42, CONFIG, SectorKey(key.x + 1, key.y))["elevation_m"]
    north = generate_sector(42, CONFIG, SectorKey(key.x, key.y + 1))["elevation_m"]
    assert [row[-1] for row in a] == [row[0] for row in east]
    assert a[-1] == north[0]
    assert a[0][0] == elevation_at(42, CONFIG, key.x * CONFIG.sector_m, key.y * CONFIG.sector_m)


def test_field_is_continuous_at_macro_seams_and_wrap():
    assert [elevation_at(42, CONFIG, x, y) for x, y in
            [(0, 0), (777_777, 512_000), (40_960_000, 20_480_000)]] == [5871, 2835, 5331]
    for x in (0, CONFIG.macro_cell_m, CONFIG.width_m):
        for y in (0, 777_777, CONFIG.height_m):
            center = elevation_at(42, CONFIG, x, y)
            assert abs(center - elevation_at(42, CONFIG, x - 1, y)) <= 1
            assert abs(center - elevation_at(42, CONFIG, x + 1, y)) <= 1
    y = CONFIG.macro_cell_m
    assert abs(elevation_at(42, CONFIG, 777_777, y - 1) - elevation_at(42, CONFIG, 777_777, y + 1)) <= 2


def test_partition_bounds_and_bounded_preparation():
    assert sector_at(CONFIG, -1, 0) == SectorKey(2559, 0)
    assert sector_at(CONFIG, CONFIG.width_m, CONFIG.height_m) == SectorKey(0, 1279)
    assert sector_at(CONFIG, 16000, 16000) == SectorKey(1, 1)
    assert canonical_sector(CONFIG, SectorKey(-1, 0)) == SectorKey(2559, 0)
    keys = nearby_sectors(CONFIG, SectorKey(0, 0))
    assert keys[0] == SectorKey(0, 0)
    assert len(keys) == 6
    assert SectorKey(2559, 0) in keys
    with pytest.raises(ValueError):
        nearby_sectors(CONFIG, SectorKey(0, 0), 5)
    with pytest.raises(ValueError):
        sector_at(CONFIG, 0, -1)
    with pytest.raises(ValueError):
        canonical_sector(CONFIG, SectorKey(0, 1280))


@pytest.mark.parametrize("kwargs", [{"generator_version": 2}, {"width_m": 0},
    {"sector_m": 123}, {"sample_step_m": 1}, {"unknown": 3}, {"height_m": True}])
def test_invalid_or_unknown_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        WorldConfig(**kwargs)


def test_sparse_persistence_order_and_reload(db_session):
    first = create_campaign(db_session, "First", world_seed=71)
    second = create_campaign(db_session, "Second", world_seed=71)
    for campaign in (first, second):
        initialize_world(db_session, campaign.id)
    assert db_session.query(GenesisSector).count() == 0
    keys = [SectorKey(31, 32), SectorKey(32, 32), SectorKey(31, 33)]
    forward = {key: materialize_sector(db_session, first.id, key).baseline for key in keys}
    reverse = {key: materialize_sector(db_session, second.id, key).baseline for key in reversed(keys)}
    assert forward == reverse
    sector = materialize_sector(db_session, first.id, keys[0])
    sector.changes = {"terrain_events": [{"kind": "landslide", "minute": 720}]}
    ids = first.id, second.id
    db_session.commit()
    # Separate session proves reads come from the save, not the identity map.
    with Session(db_session.get_bind()) as reopened:
        loaded = materialize_sector(reopened, ids[0], keys[0])
        assert loaded.baseline == forward[keys[0]]
        assert loaded.changes["terrain_events"][0]["kind"] == "landslide"
        assert reopened.query(GenesisSector).count() == 6
        assert initialize_world(reopened, ids[0]).world_seed == 71


def test_existing_baseline_is_not_regenerated(db_session, monkeypatch):
    campaign = create_campaign(db_session, "Keep", world_seed=5)
    initialize_world(db_session, campaign.id)
    saved = materialize_sector(db_session, campaign.id, SectorKey(0, 0))
    def forbidden(*args):
        raise AssertionError("Persisted terrain must not regenerate")
    monkeypatch.setattr("app.game.world.genesis.service.generate_sector", forbidden)
    assert materialize_sector(db_session, campaign.id, SectorKey(2560, 0)) is saved
    with pytest.raises(ValueError):
        initialize_world(db_session, campaign.id, WorldConfig(sea_level_m=100))
    campaign.world_seed = 6
    with pytest.raises(ValueError):
        initialize_world(db_session, campaign.id)


def test_opt_in_rollback_and_delete_are_campaign_scoped(db_session):
    a = create_campaign(db_session, "A", world_seed=1)
    b = create_campaign(db_session, "B", world_seed=2)
    assert db_session.query(GenesisWorld).count() == 0
    for campaign in (a, b):
        initialize_world(db_session, campaign.id)
        materialize_sector(db_session, campaign.id, SectorKey(0, 0))
    db_session.commit()
    materialize_sector(db_session, a.id, SectorKey(1, 0))
    db_session.rollback()
    assert db_session.query(GenesisSector).count() == 2
    assert delete_campaign(db_session, a.id)
    assert db_session.query(GenesisWorld).one().campaign_id == b.id
    assert db_session.query(GenesisSector).one().campaign_id == b.id


def test_requires_explicit_initialization_and_supported_versions(db_session):
    campaign = create_campaign(db_session, "A", world_seed=1)
    with pytest.raises(ValueError):
        materialize_sector(db_session, campaign.id, SectorKey(0, 0))
    with pytest.raises(ValueError):
        initialize_world(db_session, "missing")
    world = initialize_world(db_session, campaign.id)
    world.config = {**world.config, "generator_version": 999}
    with pytest.raises(ValueError):
        materialize_sector(db_session, campaign.id, SectorKey(0, 0))


def test_additive_migration_preserves_legacy_save(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    def migrate(target):
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", target],
                       env=env, check=True, capture_output=True, text=True)
    migrate("g15g1b2c3d4e")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO campaigns (id, name, world_seed, created_at) "
                           "VALUES ('legacy', 'Keep', 42, '2026-10-25 00:00:00')")
        before = connection.execute("SELECT * FROM campaigns").fetchall()
    migrate("head")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM campaigns").fetchall() == before
        assert connection.execute("SELECT count(*) FROM genesis_worlds").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM genesis_sectors").fetchone() == (0,)
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "g15g1b2c3d4e"],
                   env=env, check=True, capture_output=True, text=True)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM campaigns").fetchall() == before
