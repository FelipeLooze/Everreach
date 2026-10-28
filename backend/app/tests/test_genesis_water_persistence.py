import json
import os
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app.db.models.world_water import GenesisWaterPlan, GenesisWaterSector
from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
from app.game.world.genesis.water.config import WaterConfig
from app.game.world.genesis.water.service import (
    clear_water_cache, water_cache_size, initialize_water_balance, get_water_plan, materialize_water_sector,
)
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.service import initialize_hydrology, get_hydrology_plan
from app.game.world.genesis.hydrology.regional_service import initialize_regional_hydrology, materialize_hydrology_region
from app.game.world.genesis.climate.config import ClimateConfig
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.climate.service import initialize_climate
from app.game.world.genesis.sphere_topology import CellKey, cell_at
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.seed import create_campaign
from app.game.world.reset import delete_campaign


@pytest.fixture(autouse=True)
def clean_cache():
    clear_water_cache()
    yield
    clear_water_cache()


def world(db, name="W1", seed=42, climate_version=2):
    campaign = create_campaign(db, name, world_seed=seed)
    initialize_world(db, campaign.id, FormationConfigV4(macro_level=2))
    initialize_hydrology(db, campaign.id, HydrologyConfig(level=2))
    initialize_regional_hydrology(db, campaign.id)
    initialize_climate(db, campaign.id, (ClimateConfigV2 if climate_version == 2 else ClimateConfig)(level=3))
    return campaign


def test_water_opt_in_no_automatic_materialization_and_legacy_climate(db_session):
    campaign = world(db_session)
    with pytest.raises(ValueError, match="explicitly"):
        get_water_plan(db_session, campaign.id)
    row = initialize_water_balance(db_session, campaign.id)
    assert initialize_water_balance(db_session, campaign.id) is row
    assert db_session.query(GenesisHydrologyRegion).count() == db_session.query(GenesisWaterSector).count() == 0
    with pytest.raises(ValueError, match="reconfigure"):
        initialize_water_balance(db_session, campaign.id, WaterConfig(soil_capacity_mm=300))
    legacy = world(db_session, "C1", climate_version=1)
    with pytest.raises(ValueError, match="C1 needs explicit"):
        initialize_water_balance(db_session, legacy.id)
    assert initialize_water_balance(db_session, legacy.id, WaterConfig(source_climate_version=1)).water_version == 1


def test_fixed_manifest_order_reload_saved_changes_and_deferred_payload(db_session, monkeypatch):
    a, b = world(db_session, "A"), world(db_session, "B")
    h1 = get_hydrology_plan(db_session, a.id)
    nodes = [5, h1.drainage.parent[5]]
    for campaign, selected in ((a, nodes), (b, list(reversed(nodes)))):
        initialize_water_balance(db_session, campaign.id, regional_nodes=selected)
    first, second = get_water_plan(db_session, a.id), get_water_plan(db_session, b.id)
    assert first.to_dict() == second.to_dict()
    key = cell_at(geometry(2).points[5], 13)
    saved = materialize_water_sector(db_session, a.id, key)
    saved.changes = {"events": [{"kind": "future_water_event", "minute": 1000}]}
    baseline = saved.baseline
    ids = a.id, b.id
    db_session.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError("Saved W1 must not regenerate or extend geography")
    monkeypatch.setattr("app.game.world.genesis.water.service.build_water_plan", forbidden)
    monkeypatch.setattr("app.game.world.genesis.water.plan.solve", forbidden)
    with Session(db_session.get_bind()) as reopened:
        row = reopened.get(GenesisWaterPlan, ids[0])
        assert "plan" in inspect(row).unloaded
        assert get_water_plan(reopened, ids[0]).signature == first.signature
        assert "plan" in inspect(row).unloaded
        stored = materialize_water_sector(reopened, ids[0], key)
        assert stored.baseline == baseline and stored.changes["events"][0]["minute"] == 1000
    clear_water_cache()
    with Session(db_session.get_bind()) as reopened:
        loaded = get_water_plan(reopened, ids[0])
        assert loaded.to_dict() == first.to_dict()
        assert reopened.query(GenesisWaterSector).count() == 1


def test_exploration_cannot_extend_fixed_evidence_or_change_baseline(db_session):
    campaign = world(db_session)
    row = initialize_water_balance(db_session, campaign.id)
    before = json.dumps(row.plan, sort_keys=True)
    materialize_hydrology_region(db_session, campaign.id, 5)
    assert get_water_plan(db_session, campaign.id).manifest == ()
    with pytest.raises(ValueError, match="exploration"):
        initialize_water_balance(db_session, campaign.id, regional_nodes=[5])
    with pytest.raises(ValueError, match="integers"):
        initialize_water_balance(db_session, campaign.id, regional_nodes=[True])
    assert json.dumps(row.plan, sort_keys=True) == before


def test_changed_evidence_and_corrupt_water_fail_without_regeneration(db_session):
    campaign = world(db_session)
    row = initialize_water_balance(db_session, campaign.id, regional_nodes=[5])
    region = db_session.get(GenesisHydrologyRegion, (campaign.id, 5))
    region.changes = {"events": ["altered route"]}
    with pytest.raises(ValueError, match="event-aware"):
        get_water_plan(db_session, campaign.id)
    region.changes = {}
    row.water_version = 2
    with pytest.raises(ValueError):
        get_water_plan(db_session, campaign.id)
    row.water_version = 1
    row.plan = {**row.plan, "year_days": 1}
    clear_water_cache()
    with pytest.raises(ValueError, match="checksum"):
        get_water_plan(db_session, campaign.id)


def test_water_cache_rollback_scoped_deletion_and_invalid_requests(db_session):
    campaigns = [world(db_session, f"W{i}", seed=i) for i in range(3)]
    for campaign in campaigns:
        initialize_water_balance(db_session, campaign.id)
    assert water_cache_size() == 2
    db_session.commit()
    key = CellKey(0, 13, 1, 1)
    materialize_water_sector(db_session, campaigns[0].id, key)
    db_session.rollback()
    assert db_session.query(GenesisWaterSector).count() == 0
    materialize_water_sector(db_session, campaigns[1].id, key)
    assert delete_campaign(db_session, campaigns[0].id)
    assert db_session.query(GenesisWaterPlan).count() == 2
    assert db_session.query(GenesisWaterSector).one().campaign_id == campaigns[1].id
    with pytest.raises(ValueError):
        materialize_water_sector(db_session, campaigns[1].id, CellKey(0, 12, 1, 1))
    pending = world(db_session, "Pending", seed=999)
    db_session.commit()
    initialize_water_balance(db_session, pending.id)
    db_session.rollback()
    with pytest.raises(ValueError):
        get_water_plan(db_session, pending.id)


def test_additive_water_migration_preserves_all_prior_versions_and_sources(tmp_path):
    from app.db.database import enable_sqlite_foreign_keys
    path = tmp_path/"water_upgrade.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    def migrate(command, target):
        subprocess.run([sys.executable, "-m", "alembic", command, target], env=env,
                       check=True, capture_output=True, text=True)
    migrate("upgrade", "l20l3g4h5i6j")
    engine = create_engine(env["DATABASE_URL"])
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    with Session(engine) as session:
        campaign = world(session)
        cid = campaign.id
        parent = get_hydrology_plan(session, cid).drainage.parent[5]
        for node in (5, parent):
            materialize_hydrology_region(session, cid, node)
        world(session, "Legacy C1", climate_version=1)
        session.commit()
    tables = ("campaigns", "genesis_worlds", "genesis_hydrology_plans", "genesis_hydrology_refinements",
              "genesis_hydrology_regions", "genesis_climate_plans")
    def rows():
        with sqlite3.connect(path) as connection:
            return {t: connection.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
    before = rows()
    migrate("upgrade", "head")
    assert rows() == before
    with Session(engine) as session:
        assert session.query(GenesisWaterPlan).count() == 0
        initialize_water_balance(session, cid, regional_nodes=[parent, 5])
        materialize_water_sector(session, cid, CellKey(0, 13, 10, 20))
        session.commit()
        clear_water_cache()
        assert get_water_plan(session, cid).config.water_version == 1
    assert rows() == before
    engine.dispose()
    migrate("downgrade", "l20l3g4h5i6j")
    assert rows() == before
