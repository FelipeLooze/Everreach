from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from app.db.models.world_hydro_geometry import GenesisHydroGeometryPlan, GenesisHydroGeometryEvidence
from app.db.models.world_hydrology_regional import GenesisHydrologyRegion
from app.game.world.seed import create_campaign
from app.game.world.reset import delete_campaign
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.service import initialize_hydrology
from app.game.world.genesis.hydrology.regional_service import initialize_regional_hydrology
from app.game.world.genesis.climate.service import initialize_climate
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.water.service import initialize_water_balance, get_water_plan
from app.game.world.genesis.terrain.service import initialize_terrain, materialize_terrain_tile
from app.game.world.genesis.terrain.address import TerrainTile, tile_at
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.hydro_geometry.config import G1Config, GeometryRequest, Anchor
from app.game.world.genesis.hydro_geometry.service import (initialize_geometry, get_geometry_plan, materialize_geometry,
    prepare_regional_geometry, get_geometry, clear_geometry_cache, geometry_cache_size)
from app.game.world.genesis.hydro_geometry.water_evidence import water_evidence


@pytest.fixture(autouse=True)
def cache():
    clear_geometry_cache()
    yield
    clear_geometry_cache()


def world(db, name="G1", seed=42):
    c = create_campaign(db, name, world_seed=seed)
    initialize_world(db, c.id, FormationConfigV4(macro_level=2))
    initialize_hydrology(db, c.id, HydrologyConfig(level=2))
    initialize_regional_hydrology(db, c.id)
    initialize_terrain(db, c.id)
    return c


def local_request(tile=None):
    tile = tile or tile_at(SurfacePoint(3, 2, 1), 20)
    return GeometryRequest(tile=list(vars(tile).values()), grid_intervals=4,
        anchors=[Anchor(id="in", point=list(tile.point(0, 2, 4).xyz), role="ingress"),
                 Anchor(id="out", point=list(tile.point(4, 2, 4).xyz), role="outlet")])


def test_opt_in_and_no_automatic_world_conversion(db_session):
    c = world(db_session)
    with pytest.raises(ValueError, match="explicitly"):
        get_geometry_plan(db_session, c.id)
    row = initialize_geometry(db_session, c.id)
    assert initialize_geometry(db_session, c.id) is row
    assert db_session.query(GenesisHydroGeometryEvidence).count() == 0
    assert db_session.query(GenesisHydrologyRegion).count() == 0
    with pytest.raises(ValueError, match="reconfigure"):
        initialize_geometry(db_session, c.id, G1Config(section_step_m=20))


def test_regional_reload_never_resamples_even_candidate_selection(db_session, monkeypatch):
    c = world(db_session)
    initialize_geometry(db_session, c.id)
    row = prepare_regional_geometry(db_session, c.id, 5, candidate_ports=True)
    data, cid, rid = deepcopy(row.baseline), c.id, row.request_id
    row.changes = {"events": [{"id": "future-geometry-event"}]}
    db_session.commit()
    clear_geometry_cache()
    def forbidden(*args, **kwargs):
        raise AssertionError("Saved G1 must not reprocess terrain, ports, or regional geometry")
    monkeypatch.setattr("app.game.world.genesis.hydro_geometry.service.build_geometry", forbidden)
    monkeypatch.setattr("app.game.world.genesis.hydro_geometry.service.regional_request", forbidden)
    monkeypatch.setattr("app.game.world.genesis.terrain.field.TerrainSampler.sample", forbidden)
    with Session(db_session.get_bind()) as reopened:
        saved = reopened.get(GenesisHydroGeometryEvidence, (cid, rid))
        assert "baseline" in inspect(saved).unloaded
        assert prepare_regional_geometry(reopened, cid, 5, candidate_ports=True).baseline == data
        with pytest.raises(ValueError, match="overlay"):
            get_geometry(reopened, cid, rid)
        record = get_geometry(reopened, cid, rid, baseline_only=True)
        assert record["changes"]["events"][0]["id"] == "future-geometry-event"


def test_t1_events_inside_unsampled_footprint_or_peer_face_invalidate(db_session):
    c = world(db_session)
    initialize_geometry(db_session, c.id)
    req = local_request(TerrainTile(0, 20, 2**20-1, 500000))
    row = materialize_geometry(db_session, c.id, req)
    # +Y chart owns a tile sharing +X's outer edge; it can contain a live event
    # even when no route or exact sampled point happens to pass through it.
    from app.game.world.genesis.hydro_geometry.spatial import tile_neighbor
    peer = tile_neighbor(TerrainTile(*req.tile), "east")
    changed = materialize_terrain_tile(db_session, c.id, peer)
    changed.changes = {"events": [{"id": "landslide"}]}
    with pytest.raises(ValueError, match="T1 events"):
        get_geometry(db_session, c.id, row.request_id)
    assert get_geometry(db_session, c.id, row.request_id, baseline_only=True)["baseline"] == row.baseline
    changed.changes = {}
    assert get_geometry(db_session, c.id, row.request_id)["baseline"] == row.baseline


def test_hr1_events_and_corrupt_saved_proof_fail_closed(db_session):
    c = world(db_session)
    initialize_geometry(db_session, c.id)
    row = prepare_regional_geometry(db_session, c.id, 5)
    hr = db_session.get(GenesisHydrologyRegion, (c.id, 5))
    hr.changes = {"events": [{"id": "changed-route"}]}
    with pytest.raises(ValueError, match="HR1 evidence/events"):
        get_geometry(db_session, c.id, row.request_id)
    hr.changes = {}
    row.baseline_checksum = "broken"
    with pytest.raises(ValueError, match="checksum"):
        get_geometry(db_session, c.id, row.request_id)


def test_water_join_preserves_ledger_manifest_and_no_allocation(db_session):
    c = world(db_session)
    initialize_climate(db_session, c.id, ClimateConfigV2(level=3))
    saved_water = initialize_water_balance(db_session, c.id)
    initialize_geometry(db_session, c.id)
    before = checksum(saved_water.plan)
    row = prepare_regional_geometry(db_session, c.id, 5)
    record = water_evidence(row.baseline, get_water_plan(db_session, c.id))
    assert record["water_allocation_liters"] is None
    assert record["active_river_authorized"] is record["w1_manifest_extended"] is False
    assert record["w1_macro_reference"]["periods"]
    assert checksum(saved_water.plan) == before and saved_water.manifest == []
    corrupt = deepcopy(row.baseline)
    corrupt["hydrology_signature"] = "other-world"
    with pytest.raises(ValueError, match="mismatch"):
        water_evidence(corrupt, get_water_plan(db_session, c.id))


def test_rollback_bound_cache_and_scoped_reset(db_session):
    campaigns = [world(db_session, str(i), seed=i) for i in range(3)]
    for c in campaigns:
        initialize_geometry(db_session, c.id)
        get_geometry_plan(db_session, c.id)
    assert geometry_cache_size() <= 2
    db_session.commit()
    ids = [c.id for c in campaigns]
    materialize_geometry(db_session, ids[0], local_request())
    db_session.rollback()
    assert db_session.query(GenesisHydroGeometryEvidence).count() == 0
    for cid in ids:
        materialize_geometry(db_session, cid, local_request())
    delete_campaign(db_session, ids[0])
    assert db_session.get(GenesisHydroGeometryPlan, ids[0]) is None
    assert db_session.query(GenesisHydroGeometryEvidence).count() == 2


def test_migration_is_additive_and_downgrade_preserves_old_payloads(tmp_path):
    path = tmp_path/"g1_migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    cwd = Path(__file__).resolve().parents[2]
    def migrate(command, revision):
        subprocess.run([sys.executable, "-m", "alembic", command, revision], cwd=cwd, env=env,
                       check=True, capture_output=True, text=True)
    migrate("upgrade", "n22n5i6j7k8l")
    with sqlite3.connect(path) as db:
        before = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        db.execute("INSERT INTO genesis_terrain_plans(campaign_id,terrain_version,signature,source_checksum,config,plan) VALUES ('old',1,'sig','hash','{}','{\"sentinel\":7}')")
    migrate("upgrade", "o23o6j7k8l9m")
    with sqlite3.connect(path) as db:
        after = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert all(after[name] == sql for name, sql in before.items())
        assert db.execute("SELECT COUNT(*) FROM genesis_hydro_geometry_plans").fetchone()[0] == 0
        assert db.execute("SELECT plan FROM genesis_terrain_plans WHERE campaign_id='old'").fetchone()[0] == '{"sentinel":7}'
    migrate("downgrade", "n22n5i6j7k8l")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT plan FROM genesis_terrain_plans WHERE campaign_id='old'").fetchone()[0] == '{"sentinel":7}'


def test_pending_evidence_is_persisted_and_never_retried_silently(db_session, monkeypatch):
    c = world(db_session)
    initialize_geometry(db_session, c.id)
    req = GeometryRequest.model_validate({**local_request().model_dump(), "sample_budget": 16})
    row = materialize_geometry(db_session, c.id, req)
    assert row.baseline["status"] == "pending_budget"
    before = deepcopy(row.baseline)
    def forbidden(*args, **kwargs):
        raise AssertionError("Pending is persisted evidence, not permission to regenerate")
    monkeypatch.setattr("app.game.world.genesis.hydro_geometry.service.build_geometry", forbidden)
    assert materialize_geometry(db_session, c.id, req).baseline == before


def test_persisted_t1_events_and_header_version_are_detected(db_session):
    c = world(db_session)
    header = initialize_geometry(db_session, c.id)
    req = local_request()
    row = materialize_geometry(db_session, c.id, req)
    tile = materialize_terrain_tile(db_session, c.id, TerrainTile(*req.tile))
    tile.changes = {"events": [{"id": "dig"}]}
    cid, rid = c.id, row.request_id
    db_session.commit()
    with Session(db_session.get_bind()) as reopened:
        with pytest.raises(ValueError, match="T1 events"):
            get_geometry(reopened, cid, rid)
        assert get_geometry(reopened, cid, rid, baseline_only=True)["baseline"]["request_id"] == rid
    header.geometry_version = 2
    with pytest.raises(ValueError, match="version"):
        get_geometry_plan(db_session, cid)
