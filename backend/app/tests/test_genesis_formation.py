import json
import os
import subprocess
import sys
import tracemalloc

import pytest
from sqlalchemy.orm import Session

from app.db.models.region import Region
from app.db.models.location import Location
from app.db.models.world_genesis import GenesisSector, GenesisWorld
from app.db.models.world_spatial import GenesisSphereSector
from app.game.world.genesis.config import WorldConfig
from app.game.world.genesis.coordinates import SectorKey
from app.game.world.genesis.formation_config import FormationConfig, calibrated_scale
from app.game.world.genesis.formation_geography import generate_sector, sample_at
from app.game.world.genesis.formation_noise import UNIT, unit_direction
from app.game.world.genesis.formation_plan import (
    build_plan, cell_index, identify_components, indexed_cell, load_plan,
)
from app.game.world.genesis.formation_plates import MAX_PLATES, Plate, nucleate_plates
from app.game.world.genesis.formation_preview import write_preview
from app.game.world.genesis.formation_tectonics import evaluate
from app.game.world.genesis.service import initialize_world, materialize_sector
from app.game.world.genesis.spatial import bind_location, prepare_location_sector
from app.game.world.genesis.sphere_config import SphereConfig, parse_config
from app.game.world.genesis.sphere_metric import distance_m
from app.game.world.genesis.sphere_topology import (
    CellKey, DIRECTIONS, SurfacePoint, cell_center, edge_points, neighbor,
)
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign


@pytest.fixture(scope="module")
def plan():
    return build_plan(42, FormationConfig(macro_level=4, sample_intervals=2))


def test_reference_radius_is_calibrated_and_configuration_roundtrips():
    config = FormationConfig()
    assert config.radius_m == 63_710_000
    assert config.sector_level == 13  # v2 used level 10 at one tenth this radius
    assert config.macro_level == 5
    assert parse_config(config.model_dump()) == config
    assert calibrated_scale(config)["nominal_sector_span_m"] <= config.target_sector_m
    earth = FormationConfig(radius_m=6_371_000)
    assert earth.sector_level < config.sector_level
    assert calibrated_scale(earth)["plate_length_m"] < calibrated_scale(config)["plate_length_m"]
    assert FormationConfig(sector_level=9, macro_level=2).sector_level == 9
    # Explicit level overrides are pinned, not recomputed on reopening.
    assert parse_config(FormationConfig(sector_level=9).model_dump()).sector_level == 9


@pytest.mark.parametrize("kwargs", [{"macro_level": 6}, {"radius_m": 0}, {"radius_m": True},
    {"target_sector_m": 0}, {"continental_crust_ppm": -1}, {"generator_version": 2},
    {"config_version": 4}, {"sample_intervals": True}])
def test_bad_v3_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        FormationConfig(**kwargs)


def test_huge_scale_has_explicit_resource_and_resolution_limits():
    config = FormationConfig(radius_m=1_000_000_000_000)
    scale = calibrated_scale(config)
    assert config.sector_level == 24
    assert scale["sector_resolution_limited"]
    assert scale["macro_cells"] <= 6144
    assert scale["plate_length_m"] >= config.radius_m//8
    giant = build_plan(117, config)
    assert 2 <= len(giant.plates) <= MAX_PLATES == 384
    assert len(giant.labels) == 6144
    assert len(json.dumps(giant.to_dict())) < 1_000_000
    sample = generate_sector(giant, CellKey(4, config.sector_level, 0, 0))
    assert len(sample["geology"]) == 5


def test_plan_memory_is_bounded_and_cache_is_bounded():
    tracemalloc.start()
    try:
        measured = build_plan(109, FormationConfig(macro_level=2))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(measured.labels) == 96
    assert peak < 12_000_000
    assert build_plan.cache_info().maxsize == 2


def test_nucleation_is_seeded_and_not_a_requested_continent_count():
    config = FormationConfig(macro_level=2)
    counts = [len(nucleate_plates(seed, config)) for seed in range(4)]
    assert len(set(counts)) > 1
    plates = nucleate_plates(42, config)
    assert plates == nucleate_plates(42, config)
    assert any(p.continental for p in plates) and any(not p.continental for p in plates)
    # All-ocean/all-continental crust settings are valid physical inputs.
    assert not any(p.continental for p in nucleate_plates(42, FormationConfig(continental_crust_ppm=0)))
    assert all(p.continental for p in nucleate_plates(42, FormationConfig(continental_crust_ppm=1_000_000)))


def test_generation_order_and_process_hash_randomization_do_not_change_plan_or_sectors(plan):
    keys = [CellKey(0, 13, 8191, 4096), CellKey(2, 13, 0, 4096), CellKey(4, 13, 200, 300)]
    forward = {key: generate_sector(plan, key) for key in keys}
    reverse = {key: generate_sector(plan, key) for key in reversed(keys)}
    assert forward == reverse
    source = ("import json; from app.game.world.genesis.formation_config import FormationConfig; "
              "from app.game.world.genesis.formation_plan import build_plan; "
              "from app.game.world.genesis.formation_geography import sample_at; "
              "from app.game.world.genesis.sphere_topology import SurfacePoint; "
              "p=build_plan(42,FormationConfig(macro_level=2)); "
              "print(json.dumps([p.to_dict(),sample_at(p,SurfacePoint(1,1,0))],sort_keys=True))")
    outputs = [subprocess.check_output([sys.executable, "-c", source], text=True,
               env={**os.environ, "PYTHONHASHSEED": h}) for h in ("1", "999")]
    assert outputs[0] == outputs[1]
    import hashlib
    exported = json.loads(outputs[0])[0]
    assert hashlib.sha256(json.dumps(exported, sort_keys=True).encode()).hexdigest() == (
        "c62ac9a5292c9a01a9cb32c574a915aca3c49bf7e290b3a167062e4ce0eb4525")
    assert json.loads(outputs[0])[1]["elevation_m"] == -4717


@pytest.mark.parametrize("face", range(6))
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_all_faces_shared_sector_samples_include_identical_geology_and_ids(plan, face, direction):
    n = 2**plan.config.sector_level
    for offset in (0, n//2, n-1):
        x = 0 if direction == "west" else n-1 if direction == "east" else offset
        y = 0 if direction == "south" else n-1 if direction == "north" else offset
        key = CellKey(face, plan.config.sector_level, x, y)
        adjacent = neighbor(key, direction)
        reverse = next(d for d in DIRECTIONS if neighbor(adjacent, d) == key)
        points = edge_points(key, direction, 2)
        others = edge_points(adjacent, reverse, 2)
        assert points == others or points == others[::-1]
        samples = [sample_at(plan, p) for p in points]
        other_samples = [sample_at(plan, p) for p in others]
        assert samples == other_samples or samples == other_samples[::-1]


def test_interior_sector_boundaries_and_small_perturbations_remain_continuous(plan):
    key = CellKey(0, plan.config.sector_level, 4000, 4000)
    a, b = generate_sector(plan, key), generate_sector(plan, neighbor(key, "east"))
    assert [row[-1] for row in a["geology"]] == [row[0] for row in b["geology"]]
    for xyz in ((10**12, 10**12, 0), (10**12, 10**12, 10**12), (0, 0, 10**12)):
        values = [sample_at(plan, SurfacePoint(*(v+(i == axis) for i, v in enumerate(xyz))))["elevation_m"]
                  for axis in range(3)]
        assert max(values)-min(values) <= 4


def test_macro_components_join_across_faces_and_have_canonical_stable_ids():
    config = FormationConfig(macro_level=2)
    left = CellKey(0, 2, 3, 2)
    right = neighbor(left, "east")
    land = tuple(i in {cell_index(left), cell_index(right)} for i in range(96))
    labels, components = identify_components(42, config, land)
    label = labels[cell_index(left)]
    assert labels[cell_index(right)] == label
    assert components[label].kind == "landmass"
    assert components[label].cell_count == 2
    assert components[label].anchor_index == min(cell_index(left), cell_index(right))
    assert identify_components(42, config, land) == (labels, components)
    assert len(components) == 2  # one connected water body wraps around all faces


def test_component_queries_match_global_graph_and_report_submacro_disagreement(plan):
    assert sum(c.cell_count for c in plan.components) == 6*4**plan.config.macro_level
    for index in range(len(plan.labels)):
        point = cell_center(indexed_cell(index, plan.config.macro_level))
        assert plan.component_at(point) == plan.components[plan.labels[index]]
    # Honest resolution contract: local coast can differ from macro center.
    coarse = build_plan(42, FormationConfig(macro_level=2))
    samples = [sample_at(coarse, cell_center(CellKey(face, 4, x, y)))
               for face in range(6) for x, y in ((0, 0), (3, 8), (9, 14), (15, 15))]
    mismatches = [s for s in samples if s["identity"]["resolution_mismatch"]]
    assert mismatches
    assert all(s["identity"]["physical_component_id"] is None for s in mismatches)


def test_real_plan_has_cross_face_masses_and_long_addressable_tectonic_interactions(plan):
    faces = {}
    formations = {}
    for index, label in enumerate(plan.labels):
        key = indexed_cell(index, plan.config.macro_level)
        faces.setdefault(label, set()).add(key.face)
        point = cell_center(key)
        for structure in sample_at(plan, point)["structures"]:
            if structure["uplift_m"] >= 200:
                formations.setdefault(structure["id"], []).append(point)
    assert any(len(value) > 1 and plan.components[label].kind == "landmass" for label, value in faces.items())
    assert any(len(value) > 1 and plan.components[label].kind == "water_body" for label, value in faces.items())
    assert any(distance_m(plan.config, points[0], p) > 1_000_000
               for points in formations.values() for p in points[1:])


def _pair(continental=True, closing=True):
    axis = (0, 0, UNIT if closing else -UNIT)
    return (Plate(0, unit_direction(SurfacePoint(10, -4, 0)), axis, continental, 90, 80),
            Plate(1, unit_direction(SurfacePoint(10, 4, 0)), tuple(-v for v in axis), continental, 130, 80))


def test_extended_orogen_has_traceable_collision_cause_and_rift_has_opposite_effect():
    config = FormationConfig(macro_level=2)
    peaks = []
    for z in (-200_000, -100_000, 0, 100_000, 200_000):
        line = [(SurfacePoint(1_000_000, y, z), evaluate(42, config, _pair(), SurfacePoint(1_000_000, y, z)))
                for y in range(-200_000, 200_001, 1_000)]
        point, highest = max(line, key=lambda item: item[1]["terms_m"]["tectonic"])
        assert highest["terms_m"]["tectonic"] > 2500
        assert any(s["mechanism"] == "continental_collision" and s["uplift_m"] > 0 for s in highest["structures"])
        assert sum(highest["terms_m"].values()) == highest["elevation_m"]
        rift = evaluate(42, config, _pair(closing=False), point)
        assert rift["terms_m"]["tectonic"] < 0
        peaks.append(point)
    assert distance_m(config, peaks[0], peaks[-1]) > 10_000_000  # >10,000 km continuous belt


def test_ocean_ridges_have_kinematic_cause_and_thermal_basin_below_them():
    from dataclasses import replace
    config = FormationConfig(macro_level=2)
    plates = _pair(continental=False, closing=False)
    profiles = [(SurfacePoint(1_000_000, y, 0), evaluate(42, config, plates, SurfacePoint(1_000_000, y, 0)))
                for y in range(-150_000, 150_001, 1000)]
    point, ridge = max(profiles, key=lambda item: item[1]["terms_m"]["tectonic"])
    stationary = tuple(replace(p, speed_mm_year=0) for p in plates)
    basin = evaluate(42, config, stationary, point)
    assert ridge["terms_m"]["tectonic"] > 1500
    assert basin["terms_m"]["tectonic"] == 0
    assert basin["elevation_m"] < 0
    assert ridge["elevation_m"] > basin["elevation_m"]
    assert any(s["mechanism"] == "ocean_spreading_ridge" for s in ridge["structures"])


def test_plan_roundtrip_rejects_mismatch_and_structure_ids_are_addressable(plan):
    loaded = load_plan(json.loads(json.dumps(plan.to_dict())), plan.seed, plan.config)
    assert loaded == plan
    with pytest.raises(ValueError):
        load_plan(plan.to_dict(), 43, plan.config)
    broken = plan.to_dict()
    broken["labels"] = []
    with pytest.raises(ValueError):
        load_plan(broken, plan.seed, plan.config)
    for point in (SurfacePoint(1, 1, 0), SurfacePoint(1, -1, 1), SurfacePoint(2, 3, -1)):
        sample = sample_at(plan, point)
        assert sample == sample_at(loaded, point)
        for s in sample["structures"]:
            a, b = s["plates"]
            assert s["id"] == f"{s['mechanism']}:{plan.signature}:{a}:{b}"


def test_v1_v2_v3_persist_together_and_materialized_v3_never_regenerates(db_session, monkeypatch):
    worlds = []
    for version, config, key in (
        (1, WorldConfig(), SectorKey(0, 0)), (2, SphereConfig(), CellKey(0, 10, 0, 0)),
        (3, FormationConfig(macro_level=2), CellKey(0, 13, 8191, 4096))):
        campaign = create_campaign(db_session, f"Version {version}", world_seed=42)
        world = initialize_world(db_session, campaign.id, config)
        worlds.append((campaign.id, json.dumps(world.plan, sort_keys=True), key))
        sector = materialize_sector(db_session, campaign.id, key)
        assert sector.baseline["generator_version"] == version
        sector.changes = {"events": [{"kind": "landslide", "minute": 1200}]}
    assert db_session.query(GenesisSector).count() == 1
    assert db_session.query(GenesisSphereSector).count() == 2
    db_session.commit()
    def forbidden(*args):
        raise AssertionError("Saved plan/terrain cannot regenerate")
    monkeypatch.setattr("app.game.world.genesis.service.build_plan", forbidden)
    monkeypatch.setattr("app.game.world.genesis.formation_geography.generate_sector", forbidden)
    with Session(db_session.get_bind()) as reopened:
        for campaign_id, saved, key in worlds:
            assert json.dumps(initialize_world(reopened, campaign_id).plan, sort_keys=True) == saved
            loaded = materialize_sector(reopened, campaign_id, key)
            assert loaded.changes["events"][0]["kind"] == "landslide"
        with pytest.raises(ValueError):
            initialize_world(reopened, worlds[1][0], FormationConfig(macro_level=2))
        with pytest.raises(ValueError):
            initialize_world(reopened, worlds[2][0], FormationConfig(macro_level=2, radius_m=100_000_000))
    # New terrain uses the saved global plan; the global builder is still forbidden.
    monkeypatch.setattr("app.game.world.genesis.formation_geography.generate_sector", generate_sector)
    with Session(db_session.get_bind()) as reopened:
        campaign_id, _, key = worlds[2]
        next_sector = materialize_sector(reopened, campaign_id, neighbor(key, "east"))
        assert next_sector.baseline["generator_version"] == 3


def test_sparse_v3_start_uses_existing_spatial_contract_and_transaction(db_session):
    campaign = create_campaign(db_session, "Formation", world_seed=42)
    config = FormationConfig(macro_level=2)
    initialize_world(db_session, campaign.id, config)
    assert db_session.query(GenesisSphereSector).count() == 0
    region = Region(campaign_id=campaign.id, name="Gameplay region")
    db_session.add(region)
    db_session.flush()
    loc = Location(region_id=region.id, name="Explicit physical anchor")
    db_session.add(loc)
    db_session.flush()
    key = CellKey(0, config.sector_level, 100, 200)
    bind_location(db_session, campaign.id, loc.id, cell_center(key))
    prepared = prepare_location_sector(db_session, campaign.id, loc.id)
    assert prepared.baseline["generator_version"] == 3
    assert db_session.query(GenesisSphereSector).count() == 1
    db_session.commit()
    materialize_sector(db_session, campaign.id, neighbor(key, "east"))
    db_session.rollback()
    assert db_session.query(GenesisSphereSector).count() == 1
    assert delete_campaign(db_session, campaign.id)
    assert db_session.query(GenesisWorld).count() == db_session.query(GenesisSphereSector).count() == 0


def test_v3_authoritative_geography_stays_out_of_unknown_player_map(db_session):
    from app.core.enums import DiscoveryStatus
    from app.game.character.service import create_character
    from app.game.discovery.service import set_location_discovery
    from app.game.map.view import get_map_view
    from app.game.world.genesis.spatial_view import known_spatial_locations
    campaign = create_campaign(db_session, "No geography leak", world_seed=42)
    initialize_world(db_session, campaign.id, FormationConfig(macro_level=2))
    region = Region(campaign_id=campaign.id, name="Hidden physical region")
    db_session.add(region)
    db_session.flush()
    loc = Location(region_id=region.id, name="Unknown place")
    db_session.add(loc)
    db_session.flush()
    bind_location(db_session, campaign.id, loc.id, SurfacePoint(1, 1, 0))
    prepare_location_sector(db_session, campaign.id, loc.id)
    character = create_character(db_session, campaign.id, "Observer", region.id, loc.id)
    assert get_map_view(db_session, campaign.id, character.id).locations == []
    assert known_spatial_locations(db_session, campaign.id, character.id) == {}
    set_location_discovery(db_session, character.id, loc.id, DiscoveryStatus.DISCOVERED)
    assert known_spatial_locations(db_session, campaign.id, character.id) == {}
    set_location_discovery(db_session, character.id, loc.id, DiscoveryStatus.VISITED)
    assert known_spatial_locations(db_session, campaign.id, character.id) == {loc.id: [1, 1, 0]}


def test_offline_preview_produces_inspectable_files_and_does_not_mutate_plan(plan, tmp_path):
    before = json.dumps(plan.to_dict(), sort_keys=True)
    summary = write_preview(plan, tmp_path, face_size=16)
    assert summary["height_range_m"][0] < 0 < summary["height_range_m"][1]
    assert summary["generator_version"] == 3
    assert summary["plate_count"] == len(plan.plates)
    assert json.dumps(plan.to_dict(), sort_keys=True) == before
    from PIL import Image
    for name in ("terrain.png", "components.png", "tectonics.png", "planet.png"):
        with Image.open(tmp_path/name) as img:
            assert img.width > 16 and img.height > 16
    assert json.loads((tmp_path/"summary.json").read_text())["seed"] == plan.seed
    exported = json.loads((tmp_path/"plan.json").read_text())
    assert load_plan(exported, plan.seed, plan.config) == plan
    output = subprocess.check_output([sys.executable, "-m", "scripts.preview_planet", "--plan",
        str(tmp_path/"plan.json"), "--inspect-ray", "1", "1", "0"], text=True)
    assert json.loads(output) == sample_at(plan, SurfacePoint(1, 1, 0))
