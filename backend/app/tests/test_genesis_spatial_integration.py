from dataclasses import asdict
import json
import os
import random
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import DiscoveryStatus
from app.db.models.location import Location, LocationConnection
from app.db.models.region import Region
from app.db.models.subregion import Subregion
from app.db.models.world_genesis import GenesisSector, GenesisWorld
from app.db.models.world_spatial import EntitySpatialCoverage, GenesisSphereSector, LocationSpatialAnchor
from app.game.character.service import create_character
from app.game.discovery.service import discover_connection, set_location_discovery
from app.game.map.view import get_map_view
from app.game.time.clock import advance_world_time, get_world_time
from app.game.travel.service import calculate_travel_minutes, calculate_travel_incident_chance, move_character
from app.game.world.genesis.config import WorldConfig
from app.game.world.genesis.coordinates import SectorKey
from app.game.world.genesis.service import initialize_world, materialize_sector
from app.game.world.genesis.spatial import (
    add_coverage, bind_location, connection_geographic_distance, coverage_contains,
    location_preparation_plan, prepare_location_sector,
)
from app.game.world.genesis.spatial_view import known_spatial_locations
from app.game.world.genesis.sphere_config import SphereConfig
from app.game.world.genesis.sphere_geography import generate_sector
from app.game.world.genesis.sphere_topology import CellKey, SurfacePoint, cell_center, edge_points, neighbor
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign


def setup_spatial(db, name="Sphere", seed=42):
    campaign = create_campaign(db, name, world_seed=seed)
    config = SphereConfig()
    world = initialize_world(db, campaign.id, config)
    region = Region(campaign_id=campaign.id, name=f"{name} territory")
    db.add(region)
    db.flush()
    return campaign, config, world, region


def test_v1_and_v2_dispatch_are_explicit_and_existing_snapshots_remain_unchanged(db_session):
    a = create_campaign(db_session, "Legacy", world_seed=7)
    v1 = initialize_world(db_session, a.id)
    old = materialize_sector(db_session, a.id, SectorKey(0, 0))
    before = json.dumps({"config": v1.config, "plan": v1.plan, "baseline": old.baseline}, sort_keys=True)
    b, config, world, _ = setup_spatial(db_session)
    assert db_session.query(GenesisSphereSector).count() == 0
    key = CellKey(0, config.sector_level, 100, 200)
    sphere = materialize_sector(db_session, b.id, key)
    assert sphere.baseline == generate_sector(42, config, key)
    assert initialize_world(db_session, b.id) is world  # omitted config reopens pinned v2
    for campaign, wrong in ((a, key), (b, SectorKey(0, 0)), (b, CellKey(0, 0, 0, 0))):
        with pytest.raises(ValueError):
            materialize_sector(db_session, campaign.id, wrong)
    with pytest.raises(ValueError):
        initialize_world(db_session, a.id, config)
    with pytest.raises(ValueError):
        initialize_world(db_session, b.id, SphereConfig(radius_m=100_000_000))
    with pytest.raises(ValueError):
        initialize_world(db_session, b.id, WorldConfig())
    assert json.dumps({"config": v1.config, "plan": v1.plan, "baseline": old.baseline}, sort_keys=True) == before
    assert db_session.query(GenesisSector).count() == db_session.query(GenesisSphereSector).count() == 1


def test_v2_persists_in_reverse_order_reloads_and_does_not_regenerate(db_session, monkeypatch):
    a, config, _, _ = setup_spatial(db_session, "A")
    b, _, _, _ = setup_spatial(db_session, "B")
    keys = [CellKey(0, 10, 1023, 512), CellKey(2, 10, 0, 512), CellKey(4, 10, 500, 500)]
    first = {k: materialize_sector(db_session, a.id, k).baseline for k in keys}
    second = {k: materialize_sector(db_session, b.id, k).baseline for k in reversed(keys)}
    assert first == second
    sector = materialize_sector(db_session, a.id, keys[0])
    sector.changes = {"events": [{"kind": "rockfall", "minute": 900}]}
    campaign_id = a.id
    db_session.commit()
    def forbidden(*args):
        raise AssertionError("Saved geography must never regenerate")
    monkeypatch.setattr("app.game.world.genesis.sphere_geography.generate_sector", forbidden)
    with Session(db_session.get_bind()) as reopened:
        loaded = materialize_sector(reopened, campaign_id, keys[0])
        assert loaded.baseline == first[keys[0]]
        assert loaded.changes["events"][0]["kind"] == "rockfall"
        assert reopened.query(GenesisSphereSector).count() == 6


def test_sparse_coverages_and_anchor_ownership_are_persistent(db_session):
    campaign, _, _, region = setup_spatial(db_session)
    subregion = Subregion(region_id=region.id, name="Across the seam")
    location = Location(region_id=region.id, name="Local area", x=12, y=34)
    db_session.add_all([subregion, location])
    db_session.flush()
    key = CellKey(0, 10, 1023, 512)
    other = neighbor(key, "east")
    left = add_coverage(db_session, campaign.id, key.parent(4), region_id=region.id)
    right = add_coverage(db_session, campaign.id, other.parent(4), region_id=region.id)
    assert add_coverage(db_session, campaign.id, key.parent(4), region_id=region.id) is left
    add_coverage(db_session, campaign.id, other.parent(4), subregion_id=subregion.id)
    anchor = bind_location(db_session, campaign.id, location.id, cell_center(key))
    assert bind_location(db_session, campaign.id, location.id, cell_center(key)) is anchor
    assert coverage_contains(left, cell_center(key))
    assert coverage_contains(right, cell_center(other))
    for point in edge_points(key, "east"):
        assert coverage_contains(left, point) and coverage_contains(right, point)
    assert not coverage_contains(left, SurfacePoint(-1, 0, 0))
    assert (location.x, location.y) == (12, 34)
    assert db_session.query(GenesisSphereSector).count() == 0  # bindings do not materialize terrain
    with pytest.raises(ValueError):
        bind_location(db_session, campaign.id, location.id, cell_center(other))
    for kwargs in ({}, {"region_id": region.id, "subregion_id": subregion.id}):
        with pytest.raises(ValueError):
            add_coverage(db_session, campaign.id, key, **kwargs)
    other_campaign, _, _, other_region = setup_spatial(db_session, "Other", seed=3)
    with pytest.raises(ValueError):
        bind_location(db_session, other_campaign.id, location.id, cell_center(key))
    with pytest.raises(ValueError):
        add_coverage(db_session, other_campaign.id, key, subregion_id=subregion.id)
    with pytest.raises(ValueError):
        add_coverage(db_session, campaign.id, key, region_id=other_region.id)
    with pytest.raises(ValueError):
        add_coverage(db_session, campaign.id, CellKey(0, 11, 0, 0), region_id=region.id)
    location_id = location.id
    campaign_id, region_id = campaign.id, region.id
    db_session.commit()
    with Session(db_session.get_bind()) as reopened:
        assert reopened.get(LocationSpatialAnchor, location_id).point == list(cell_center(key).xyz)
        assert reopened.query(EntitySpatialCoverage).filter_by(region_id=region_id).count() == 2
        assert reopened.get(GenesisWorld, campaign_id).config["config_version"] == 2


def test_legacy_has_no_implicit_binding_and_missing_endpoints_are_explicit(db_session):
    campaign = create_campaign(db_session, "Legacy", world_seed=7)
    initialize_world(db_session, campaign.id)
    with pytest.raises(ValueError):
        bind_location(db_session, campaign.id, "unknown", SurfacePoint(1, 0, 0))
    a, _, _, region = setup_spatial(db_session)
    locations = [Location(region_id=region.id, name=name) for name in ("A", "B")]
    db_session.add_all(locations)
    db_session.flush()
    connection = LocationConnection(from_location_id=locations[0].id, to_location_id=locations[1].id)
    db_session.add(connection)
    db_session.flush()
    assert connection_geographic_distance(db_session, a.id, connection.id) is None
    with pytest.raises(ValueError):
        connection_geographic_distance(db_session, a.id, "missing")


def test_route_crosses_multiple_sectors_and_face_seam_without_revealing_unknown_places(db_session):
    campaign, config, _, region = setup_spatial(db_session)
    keys = [CellKey(0, 10, 1022, 512), CellKey(0, 10, 1023, 512),
            CellKey(2, 10, 0, 512), CellKey(2, 10, 1, 512)]
    locations = [Location(region_id=region.id, name=f"Test waypoint {i}", x=i*10, y=0)
                 for i in range(4)]
    db_session.add_all(locations)
    db_session.flush()
    for location, key in zip(locations, keys):
        bind_location(db_session, campaign.id, location.id, cell_center(key))
    character = create_character(db_session, campaign.id, "Explorer", region.id, locations[0].id)
    set_location_discovery(db_session, character.id, locations[0].id, DiscoveryStatus.VISITED)
    set_location_discovery(db_session, character.id, locations[1].id, DiscoveryStatus.DISCOVERED)
    connections = []
    for origin, destination in zip(locations, locations[1:]):
        connection = LocationConnection(from_location_id=origin.id, to_location_id=destination.id,
                                         distance=1.0, danger=0, travel_time_modifier=1.0)
        db_session.add(connection)
        db_session.flush()
        discover_connection(db_session, character.id, connection.id)
        connections.append(connection)
    initial = prepare_location_sector(db_session, campaign.id, locations[0].id)
    assert initial.baseline["cell"] == [keys[0].face, keys[0].level, keys[0].x, keys[0].y]
    plan = location_preparation_plan(db_session, campaign.id, locations[1].id, radius=1)
    assert keys[1] in plan and keys[2] in plan  # preparation crosses the seam
    assert db_session.query(GenesisSphereSector).count() == 1  # planning did not generate sectors
    before = get_map_view(db_session, campaign.id, character.id)
    assert {loc.id for loc in before.locations} == {loc.id for loc in locations[:2]}
    known_unvisited = next(loc for loc in before.locations if loc.id == locations[1].id)
    assert known_unvisited.x is known_unvisited.y is None
    assert set(known_spatial_locations(db_session, campaign.id, character.id)) == {locations[0].id}
    minute_start = get_world_time(db_session, campaign.id).total_minutes()
    for i, (key, destination, connection) in enumerate(zip(keys[1:], locations[1:], connections), start=1):
        original_duration = calculate_travel_minutes(connection)
        original_risk = calculate_travel_incident_chance(connection, original_duration)
        metres = connection_geographic_distance(db_session, campaign.id, connection.id)
        assert metres > 0
        assert connection.distance == 1.0  # explicit regression guard: no invented conversion
        prepare_location_sector(db_session, campaign.id, destination.id)
        result = move_character(db_session, campaign.id, character, destination.id, rng=random.Random(42))
        advance_world_time(db_session, campaign.id, result.minutes)
        assert result.base_minutes == original_duration == 15
        assert result.risk.chance == original_risk == 0
        assert character.location_id == destination.id
        known = known_spatial_locations(db_session, campaign.id, character.id)
        assert set(known) == {loc.id for loc in locations[:i+1]}
        assert db_session.query(GenesisSphereSector).count() == i+1
    assert get_world_time(db_session, campaign.id).total_minutes() == minute_start+45
    assert len({key.face for key in keys}) == 2
    assert {loc.id for loc in get_map_view(db_session, campaign.id, character.id).locations} == {loc.id for loc in locations}
    # Scope and campaign remain authoritative even in the spherical adapter.
    assert known_spatial_locations(db_session, campaign.id, character.id, scope="world") == {}
    other = create_campaign(db_session, "Other", world_seed=9)
    with pytest.raises(ValueError):
        known_spatial_locations(db_session, other.id, character.id)
    db_session.commit()
    ids = campaign.id, character.id
    with Session(db_session.get_bind()) as reopened:
        assert len(known_spatial_locations(reopened, *ids)) == 4
        assert len(asdict(get_map_view(reopened, *ids))["locations"]) == 4


def test_delete_and_rollback_preserve_other_worlds_with_foreign_keys_enabled(db_session):
    a, _, _, ra = setup_spatial(db_session, "A")
    b, _, _, rb = setup_spatial(db_session, "B")
    for campaign, region in ((a, ra), (b, rb)):
        loc = Location(region_id=region.id, name="Anchor")
        db_session.add(loc)
        db_session.flush()
        bind_location(db_session, campaign.id, loc.id, SurfacePoint(1, 0, 0))
        add_coverage(db_session, campaign.id, CellKey(0, 0, 0, 0), region_id=region.id)
        materialize_sector(db_session, campaign.id, CellKey(0, 10, 0, 0))
    db_session.commit()
    materialize_sector(db_session, a.id, CellKey(0, 10, 1, 0))
    db_session.rollback()
    assert db_session.query(GenesisSphereSector).count() == 2
    assert delete_campaign(db_session, a.id)
    for model in (EntitySpatialCoverage, LocationSpatialAnchor, GenesisSphereSector, GenesisWorld):
        assert db_session.query(model).one().campaign_id == b.id


def test_coverage_database_contract_rejects_missing_owner(db_session):
    campaign, _, _, _ = setup_spatial(db_session)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(EntitySpatialCoverage(campaign_id=campaign.id, face=0, level=0, x=0, y=0))
        db_session.flush()


def test_spherical_migration_preserves_populated_v1_save_and_roundtrips(tmp_path):
    path = tmp_path / "legacy_sphere_upgrade.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path.as_posix()}"}
    def alembic(command, revision):
        subprocess.run([sys.executable, "-m", "alembic", command, revision],
                       env=env, check=True, capture_output=True, text=True)
    alembic("upgrade", "h16h1c2d3e4f")
    config = WorldConfig()
    from app.game.world.genesis.geography import global_plan, generate_sector as legacy_sector
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO campaigns (id,name,world_seed,created_at) VALUES ('old','Keep',7,'2026-10-25')")
        conn.execute("INSERT INTO genesis_worlds VALUES (?,?,?,?)",
                     ("old", 7, json.dumps(config.model_dump()), json.dumps(global_plan(7, config))))
        conn.execute("INSERT INTO genesis_sectors VALUES (?,?,?,?,?)",
                     ("old", 0, 0, json.dumps(legacy_sector(7, config, SectorKey(0, 0))), '{"event":"keep"}'))
        before = {table: conn.execute(f"SELECT * FROM {table}").fetchall()
                  for table in ("campaigns", "genesis_worlds", "genesis_sectors")}
    alembic("upgrade", "head")
    with sqlite3.connect(path) as conn:
        for table, rows in before.items():
            assert conn.execute(f"SELECT * FROM {table}").fetchall() == rows
        for table in ("genesis_sphere_sectors", "location_spatial_anchors", "entity_spatial_coverages"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    # Exercise actual migrated schema through the same ORM services as runtime.
    from sqlalchemy import create_engine, event
    from app.db.database import enable_sqlite_foreign_keys
    engine = create_engine(env["DATABASE_URL"])
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    with Session(engine) as session:
        campaign, _, _, region = setup_spatial(session, "Migrated")
        loc = Location(region_id=region.id, name="Migrated anchor")
        session.add(loc)
        session.flush()
        bind_location(session, campaign.id, loc.id, SurfacePoint(1, 0, 0))
        add_coverage(session, campaign.id, CellKey(0, 0, 0, 0), region_id=region.id)
        materialize_sector(session, campaign.id, CellKey(0, 10, 1023, 512))
        session.commit()
        assert materialize_sector(session, "old", SectorKey(0, 0)).changes == {"event": "keep"}
        assert delete_campaign(session, campaign.id)
        session.commit()
    engine.dispose()
    alembic("downgrade", "h16h1c2d3e4f")
    with sqlite3.connect(path) as conn:
        for table, rows in before.items():
            assert conn.execute(f"SELECT * FROM {table}").fetchall() == rows
