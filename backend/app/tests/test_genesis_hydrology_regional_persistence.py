import json
import os
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy.orm import Session

from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_hydrology import GenesisHydrologyPlan, GenesisHydrologySector
from app.db.models.world_hydrology_regional import GenesisHydrologyRefinement, GenesisHydrologyRegion
from app.game.world.genesis.formation_plan import indexed_cell
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.regional import RegionalHydrologyConfig
from app.game.world.genesis.hydrology.regional_service import (
    initialize_regional_hydrology, materialize_hydrology_region, query_hydrology_sector,
)
from app.game.world.genesis.hydrology.service import clear_plan_cache, initialize_hydrology, materialize_hydrology_sector
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.sphere_topology import CellKey, SurfacePoint, cell_at
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign


def world(db, name="Regional"):
    campaign = create_campaign(db, name, world_seed=42)
    initialize_world(db, campaign.id, FormationConfigV4(macro_level=2))
    initialize_hydrology(db, campaign.id, HydrologyConfig(level=2))
    return campaign


def test_hr1_opt_in_does_not_modify_or_materialize_h1(db_session):
    campaign = world(db_session)
    h1 = db_session.get(GenesisHydrologyPlan, campaign.id)
    before = json.dumps(h1.plan, sort_keys=True)
    with pytest.raises(ValueError, match="explicitly"):
        materialize_hydrology_region(db_session, campaign.id, 5)
    row = initialize_regional_hydrology(db_session, campaign.id)
    assert initialize_regional_hydrology(db_session, campaign.id) is row
    assert db_session.query(GenesisHydrologyRegion).count() == db_session.query(GenesisHydrologySector).count() == 0
    assert json.dumps(h1.plan, sort_keys=True) == before
    with pytest.raises(ValueError, match="reconfigure"):
        initialize_regional_hydrology(db_session, campaign.id, RegionalHydrologyConfig(depth=4))
    legacy = create_campaign(db_session, "Legacy")
    initialize_world(db_session, legacy.id)
    with pytest.raises(ValueError):
        initialize_regional_hydrology(db_session, legacy.id)


def test_order_persisted_changes_and_reload_without_refining_again(db_session, monkeypatch):
    campaigns = [world(db_session, name) for name in ("A", "B")]
    for campaign in campaigns:
        initialize_regional_hydrology(db_session, campaign.id)
    a = {n: materialize_hydrology_region(db_session, campaigns[0].id, n).baseline for n in (5, 16)}
    b = {n: materialize_hydrology_region(db_session, campaigns[1].id, n).baseline for n in (16, 5)}
    assert a == b
    row = materialize_hydrology_region(db_session, campaigns[0].id, 5)
    row.changes = {"events": [{"kind": "future_world_change", "minute": 120}]}
    ids = [c.id for c in campaigns]
    db_session.commit()
    clear_plan_cache()
    def forbidden(*args, **kwargs):
        raise AssertionError("Returning to a prepared region must not resample terrain or solve H1")
    monkeypatch.setattr("app.game.world.genesis.hydrology.regional_service.build_regional_hydrology", forbidden)
    monkeypatch.setattr("app.game.world.genesis.hydrology.regional_service.get_hydrology_plan", forbidden)
    with Session(db_session.get_bind()) as reopened:
        saved = materialize_hydrology_region(reopened, ids[0], 5)
        assert saved.baseline == a[5] and saved.changes["events"][0]["minute"] == 120
        segment = saved.baseline["segments"][0]
        midpoint = SurfacePoint(*(x+y for x, y in zip(*segment["points"])))
        snapshot = query_hydrology_sector(reopened, ids[0], cell_at(midpoint, 13))
        assert snapshot["baseline"]["pieces"] and snapshot["changes"] == saved.changes
        assert reopened.query(GenesisHydrologyRegion).count() == 4


def test_signature_checksum_and_version_mismatches_do_not_regenerate(db_session):
    campaign = world(db_session)
    header = initialize_regional_hydrology(db_session, campaign.id)
    row = materialize_hydrology_region(db_session, campaign.id, 5)
    header.refinement_version = 2
    with pytest.raises(ValueError):
        materialize_hydrology_region(db_session, campaign.id, 5)
    header.refinement_version = 1
    row.baseline = {**row.baseline, "segments": []}
    with pytest.raises(ValueError, match="refusing regeneration"):
        materialize_hydrology_region(db_session, campaign.id, 5)
    h1 = db_session.get(GenesisHydrologyPlan, campaign.id)
    h1.payload_checksum = "changed"
    with pytest.raises(ValueError):
        materialize_hydrology_region(db_session, campaign.id, 16)


def test_rollback_and_campaign_deletion_are_scoped(db_session):
    a, b = world(db_session, "A"), world(db_session, "B")
    for campaign in (a, b):
        initialize_regional_hydrology(db_session, campaign.id)
    db_session.commit()
    materialize_hydrology_region(db_session, a.id, 5)
    db_session.rollback()
    assert db_session.query(GenesisHydrologyRegion).count() == 0
    for campaign in (a, b):
        materialize_hydrology_region(db_session, campaign.id, 5)
    assert delete_campaign(db_session, a.id)
    assert db_session.query(GenesisHydrologyRegion).one().campaign_id == b.id
    assert db_session.query(GenesisHydrologyRefinement).one().campaign_id == b.id


def test_invalid_region_and_sector_requests_fail_closed(db_session):
    campaign = world(db_session)
    initialize_regional_hydrology(db_session, campaign.id)
    for node in (-1, True, 96):
        with pytest.raises(ValueError):
            materialize_hydrology_region(db_session, campaign.id, node)
    with pytest.raises(ValueError):
        query_hydrology_sector(db_session, campaign.id, CellKey(0, 5, 0, 0))


def test_additive_hr1_migration_preserves_v4_h1_and_legacy_data(tmp_path):
    from sqlalchemy import create_engine, event
    from app.db.database import enable_sqlite_foreign_keys
    path = tmp_path/"regional_upgrade.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    def migrate(command, target):
        subprocess.run([sys.executable, "-m", "alembic", command, target], env=env,
                       check=True, capture_output=True, text=True)
    migrate("upgrade", "j18j1e2f3g4h")
    engine = create_engine(env["DATABASE_URL"])
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    with Session(engine) as session:
        campaign = world(session)
        saved_id = campaign.id
        materialize_hydrology_sector(session, saved_id, CellKey(0, 13, 10, 20))
        session.commit()
    tables = ("campaigns", "genesis_worlds", "genesis_hydrology_plans", "genesis_hydrology_sectors")
    def rows():
        with sqlite3.connect(path) as connection:
            return {t: connection.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
    before = rows()
    migrate("upgrade", "head")
    assert rows() == before
    with Session(engine) as session:
        assert session.query(GenesisHydrologyRefinement).count() == 0
        initialize_regional_hydrology(session, saved_id)
        materialize_hydrology_region(session, saved_id, 5)
        session.commit()
        assert materialize_hydrology_region(session, saved_id, 5).baseline["segments"]
    assert rows() == before
    engine.dispose()
    migrate("downgrade", "j18j1e2f3g4h")
    assert rows() == before
