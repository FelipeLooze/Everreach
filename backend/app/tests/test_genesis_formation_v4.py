import hashlib
import json
import math
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.db.models.world_spatial import GenesisSphereSector
from app.game.world.seed import create_campaign
from app.game.world.genesis.coast_refinement import build_coast_patch, fragment_at
from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_geography import generate_sector, sample_at
from app.game.world.genesis.formation_plan import build_plan, load_plan
from app.game.world.genesis.formation_plates import MAX_PLATES
from app.game.world.genesis.formation_validation import plate_site_density
from app.game.world.genesis.formation_v4 import (
    AREA_SCALE, MAX_SITE_ATTEMPTS, RANDOM_RANGE, FormationConfigV4,
    activation_thresholds, cell_area_weight, nucleate_plates_v4, sample_center,
)
from app.game.world.genesis.service import initialize_world, materialize_sector
from app.game.world.genesis.sphere_area import cell_solid_angle, rectangle_solid_angle
from app.game.world.genesis.sphere_config import parse_config
from app.game.world.genesis.sphere_topology import CellKey, DIRECTIONS, SurfacePoint, cell_center, edge_points, neighbor


@pytest.fixture(scope="module")
def plan4():
    return build_plan(42, FormationConfigV4(macro_level=2, sample_intervals=2))


def test_versions_are_explicit_and_v3_does_not_accept_v4_config():
    v4 = FormationConfigV4()
    assert v4.radius_m == 63_710_000 and v4.sector_level == 13
    assert parse_config(v4.model_dump()) == v4
    with pytest.raises(ValueError):
        FormationConfig.model_validate(v4.model_dump())
    with pytest.raises(ValueError):
        FormationConfigV4(generator_version=3)
    assert FormationConfig().generator_version == 3


def test_frozen_area_table_matches_existing_spherical_area_function():
    for slot in range(MAX_PLATES):
        face, local = divmod(slot, 64)
        y, x = divmod(local, 8)
        assert abs(cell_area_weight(slot)/AREA_SCALE-cell_solid_angle(CellKey(face, 3, x, y))) < .51/AREA_SCALE
    assert sum(cell_area_weight(s) for s in range(MAX_PLATES))/AREA_SCALE == pytest.approx(4*math.pi, abs=1e-10)


@pytest.mark.parametrize("radius", [1000, 6_371_000, 63_710_000, 637_100_000, 1_000_000_000_000])
def test_area_proportional_probability_has_no_local_saturation_at_any_radius(radius):
    thresholds = activation_thresholds(FormationConfigV4(radius_m=radius))
    assert len(thresholds) == 384
    assert 0 < min(thresholds) <= max(thresholds) <= RANDOM_RANGE*95//100
    base = cell_area_weight(0)
    for slot, threshold in enumerate(thresholds):
        weight = cell_area_weight(slot)
        # Proportionality holds to integer rounding, including the huge-radius cap.
        assert abs(threshold*base-thresholds[0]*weight) <= base+weight


def test_conditional_site_sampler_is_area_weighted_inside_the_cell():
    sites = [sample_center(seed, 0) for seed in range(4096)]
    observed = sum(p[1]/p[0] < -.875 for p in sites)/len(sites)
    expected = rectangle_solid_angle(-1, -1, -.875, -.75)/rectangle_solid_angle(-1, -1, -.75, -.75)
    assert observed == pytest.approx(expected, abs=.025)
    assert abs(expected-.5) > .025  # distinguishes uniform face-coordinate jitter
    assert all(-1 < p[1]/p[0] < -.75 and -1 < p[2]/p[0] < -.75 for p in sites)


def test_rejection_has_strict_cost_and_does_not_fall_back_to_biased_jitter(monkeypatch):
    import app.game.world.genesis.formation_v4 as module
    original, calls = module.coordinate_seed, []
    def force_rejection(seed, version, domain, *coordinates):
        if domain == "surface_accept":
            calls.append(coordinates)
            return RANDOM_RANGE-1
        return original(seed, version, domain, *coordinates)
    monkeypatch.setattr(module, "coordinate_seed", force_rejection)
    with pytest.raises(ValueError, match="fixed attempt budget"):
        sample_center(42, 0)
    assert len(calls) == MAX_SITE_ATTEMPTS == 128
    # All level-3 cells have per-attempt acceptance strictly greater than 1/2.
    for y in range(8):
        for x in range(8):
            a, b = (2*x-8, 2*(x+1)-8), (2*y-8, 2*(y+1)-8)
            nearest = lambda axis: 0 if axis[0] <= 0 <= axis[1] else min(abs(v) for v in axis)
            minimum = 64+nearest(a)**2+nearest(b)**2
            maximum = 64+max(abs(v) for v in a)**2+max(abs(v) for v in b)**2
            assert 4*minimum**3 > maximum**3


def test_structural_minimum_is_bounded_and_still_seeded_by_area(monkeypatch):
    import app.game.world.genesis.formation_v4 as module
    original = module.coordinate_seed
    def no_active_sites(seed, version, domain, *coordinates):
        return RANDOM_RANGE-1 if domain == "nucleation" else original(seed, version, domain, *coordinates)
    monkeypatch.setattr(module, "coordinate_seed", no_active_sites)
    first = nucleate_plates_v4(42, FormationConfigV4())
    assert len(first) == 2 and first[0].slot != first[1].slot
    assert first == nucleate_plates_v4(42, FormationConfigV4())
    assert first != nucleate_plates_v4(43, FormationConfigV4())


@pytest.mark.parametrize("radius", [6_371_000, 63_710_000, 637_100_000, 1_000_000_000_000])
def test_density_correction_over_multiple_seeds_and_radii(radius):
    config = FormationConfigV4(radius_m=radius)
    inventories = [SimpleNamespace(plates=nucleate_plates_v4(seed, config)) for seed in range(256)]
    density = plate_site_density(inventories)["site_density_relative_to_surface_average"]
    tolerance = .20 if radius == 6_371_000 else .08
    assert all(abs(d-1) < tolerance for d in density.values())
    assert len({len(p.plates) for p in inventories}) > 1
    assert all(2 <= len(p.plates) <= MAX_PLATES for p in inventories)


def test_v3_plan_and_r1_keep_their_pre_v4_replay_vectors():
    old = build_plan(42, FormationConfig(macro_level=2))
    digest = hashlib.sha256(json.dumps(old.to_dict(), sort_keys=True).encode()).hexdigest()
    assert digest == "c62ac9a5292c9a01a9cb32c574a915aca3c49bf7e290b3a167062e4ce0eb4525"
    assert sample_at(old, SurfacePoint(1, 1, 0))["elevation_m"] == -4717
    r1 = build_coast_patch(build_plan(42, FormationConfig()), CellKey(5, 8, 252, 244), 13)
    assert hashlib.sha256(json.dumps(r1, sort_keys=True).encode()).hexdigest() == (
        "74fbc6a267296a0614929ed0063b174a8d6ac257ad30991bd020e0f405f2f122")


def test_v4_plan_roundtrip_order_and_process_replay(plan4):
    keys = [CellKey(0, 13, 8191, 4096), CellKey(2, 13, 0, 4096), CellKey(4, 13, 100, 200)]
    assert {k: generate_sector(plan4, k) for k in keys} == {k: generate_sector(plan4, k) for k in reversed(keys)}
    interior = CellKey(0, 13, 4000, 4000)
    left, right = generate_sector(plan4, interior), generate_sector(plan4, neighbor(interior, "east"))
    assert [row[-1] for row in left["geology"]] == [row[0] for row in right["geology"]]
    assert load_plan(json.loads(json.dumps(plan4.to_dict())), plan4.seed, plan4.config) == plan4
    with pytest.raises(ValueError):
        load_plan(plan4.to_dict(), 42, FormationConfig(macro_level=2, sample_intervals=2))
    source = ("import json,hashlib; from app.game.world.genesis.formation_v4 import FormationConfigV4; "
              "from app.game.world.genesis.formation_plan import build_plan; "
              "p=build_plan(42,FormationConfigV4(macro_level=2)); "
              "print(hashlib.sha256(json.dumps(p.to_dict(),sort_keys=True).encode()).hexdigest())")
    outputs = [subprocess.check_output([sys.executable, "-c", source], text=True,
               env={**os.environ, "PYTHONHASHSEED": seed}) for seed in ("1", "789")]
    assert outputs[0].strip() == outputs[1].strip() == "9ed041ebab472246759b21e4e2095aacf8e5772055364d2eb60a66b20bd363bf"


@pytest.mark.parametrize("face", range(6))
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_v4_geography_and_r1_continue_through_all_face_seams(plan4, face, direction):
    n = 2**plan4.config.sector_level
    x = 0 if direction == "west" else n-1 if direction == "east" else n//2
    y = 0 if direction == "south" else n-1 if direction == "north" else n//2
    key = CellKey(face, plan4.config.sector_level, x, y)
    other = neighbor(key, direction)
    reverse = next(d for d in DIRECTIONS if neighbor(other, d) == key)
    a = [sample_at(plan4, p) for p in edge_points(key, direction, 2)]
    b = [sample_at(plan4, p) for p in edge_points(other, reverse, 2)]
    assert a == b or a == b[::-1]
    tile = CellKey(face, 3, 0 if direction == "west" else 7 if direction == "east" else 4,
                   0 if direction == "south" else 7 if direction == "north" else 4)
    patches = [build_coast_patch(plan4, k, 4) for k in (tile, neighbor(tile, direction))]
    ports = [{p["id"]: p for p in patch["ports"]} for patch in patches]
    shared = ports[0].keys() & ports[1].keys()
    assert len(shared) == 2
    for identifier in shared:
        assert ports[0][identifier]["continuous_kind_at_samples"] == ports[1][identifier]["continuous_kind_at_samples"]
    assert patches[0]["refinement_version"] == 1 and patches[0]["source_generator_version"] == 4
    first = patches[0]["fragments"][0]
    assert fragment_at(patches[0], cell_center(CellKey(*first["cells"][0])))["id"] == first["id"]


def test_v4_incremental_persistence_keeps_v3_and_saved_changes(db_session, monkeypatch):
    worlds = []
    for cls in (FormationConfig, FormationConfigV4):
        campaign = create_campaign(db_session, cls.__name__, world_seed=42)
        world = initialize_world(db_session, campaign.id, cls(macro_level=2))
        assert db_session.query(GenesisSphereSector).filter_by(campaign_id=campaign.id).count() == 0
        key = CellKey(0, 13, 8191, 4096)
        sector = materialize_sector(db_session, campaign.id, key)
        sector.changes = {"events": ["keep physical change"]}
        worlds.append((campaign.id, json.dumps(world.plan, sort_keys=True), json.dumps(sector.baseline, sort_keys=True)))
    db_session.commit()
    def forbidden(*args):
        raise AssertionError("Persistent plan must not regenerate")
    monkeypatch.setattr("app.game.world.genesis.service.build_plan", forbidden)
    monkeypatch.setattr("app.game.world.genesis.formation_v4.nucleate_plates_v4", forbidden)
    with Session(db_session.get_bind()) as reopened:
        for version, (campaign_id, saved_plan, saved_sector) in zip((3, 4), worlds):
            world = initialize_world(reopened, campaign_id)
            assert json.dumps(world.plan, sort_keys=True) == saved_plan
            loaded = materialize_sector(reopened, campaign_id, CellKey(0, 13, 8191, 4096))
            assert json.dumps(loaded.baseline, sort_keys=True) == saved_sector
            assert loaded.changes == {"events": ["keep physical change"]}
            new = materialize_sector(reopened, campaign_id, CellKey(2, 13, 0, 4096))
            assert new.baseline["generator_version"] == version
        with pytest.raises(ValueError):
            initialize_world(reopened, worlds[0][0], FormationConfigV4(macro_level=2))
        with pytest.raises(ValueError):
            initialize_world(reopened, worlds[1][0], FormationConfig(macro_level=2))


def test_v4_extreme_scale_remains_bounded():
    config = FormationConfigV4(radius_m=1_000_000_000_000)
    plan = build_plan(42, config)
    assert config.sector_level == 24 and len(plan.labels) == 6144
    assert 2 <= len(plan.plates) <= 384
    assert len(json.dumps(plan.to_dict())) < 1_000_000
    assert generate_sector(plan, CellKey(4, 24, 0, 0))["generator_version"] == 4


def test_v4_polar_and_vertex_neighborhoods_have_no_artificial_height_jump(plan4):
    for xyz in ((0, 0, 10**12), (0, 0, -10**12), (10**12, 10**12, 10**12)):
        values = [sample_at(plan4, SurfacePoint(*(v+(i == axis) for i, v in enumerate(xyz))))["elevation_m"]
                  for axis in range(3)]
        assert max(values)-min(values) <= 4


def test_v4_offline_tools_export_and_compare_versioned_plans(plan4, tmp_path):
    from app.game.world.genesis.formation_validation import measure_plan
    from app.game.world.genesis.validation_report import write_case, write_comparison, case_name
    output = subprocess.check_output([sys.executable, "-m", "scripts.preview_planet", "--formation-version", "4",
        "--seed", "42", "--face-size", "16", "--output", str(tmp_path/"preview")], text=True)
    assert json.loads(output)["generator_version"] == 4
    exported = json.loads((tmp_path/"preview/plan.json").read_text())
    assert exported["kind"] == "plate_formation_v4"
    inspected = subprocess.check_output([sys.executable, "-m", "scripts.preview_planet", "--plan",
        str(tmp_path/"preview/plan.json"), "--inspect-ray", "1", "1", "0"], text=True)
    full_plan = load_plan(exported, 42, parse_config(exported["config"]))
    assert json.loads(inspected) == sample_at(full_plan, SurfacePoint(1, 1, 0))
    for version, plan in ((3, build_plan(42, FormationConfig(macro_level=2, sample_intervals=2))), (4, plan4)):
        directory = tmp_path/f"v{version}"
        grid = measure_plan(plan, 3)
        grid.summary["plan_seconds"] = 0
        write_case(plan, grid, directory/case_name(42, plan.config.radius_m))
        write_comparison([grid.summary], directory)
    subprocess.run([sys.executable, "-m", "scripts.compare_tectonic_versions", "--root", str(tmp_path),
        "--density-seeds", "16"], check=True, capture_output=True, text=True)
    assert (tmp_path/"paired-reference.png").exists()
    assert (tmp_path/"density-comparison.png").exists()
