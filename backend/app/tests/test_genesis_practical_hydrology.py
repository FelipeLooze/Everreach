from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.preview_water import sources
from app.game.world.genesis.water.plan import load_water_plan
from app.game.world.genesis.terrain.field import build_terrain_plan, TerrainSampler, checksum
from app.game.world.genesis.terrain.address import TerrainTile
from app.game.world.genesis.hydro_geometry.spatial import tile_neighbor
from app.game.world.genesis.water_reconciliation.practical.config import PracticalConfig
from app.game.world.genesis.water_reconciliation.practical.allocation import split_integer, surface_quota
from app.game.world.genesis.water_reconciliation.practical.future import future_forcing_proposal, _leaf_share
from app.game.world.genesis.water_reconciliation.practical.hydraulics import icbrt, section_at_depth
from app.game.world.genesis.water_reconciliation.practical.proof import inspect_parcel
from app.game.world.genesis.water_reconciliation.practical.service import validate_proof

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def real_inputs():
    data = json.loads((ROOT/"artifacts/practical-hydrology-p1/probe.json").read_text())
    proof = data["found"]
    source, h1, climate = sources(42, 63_710_000)
    wd = json.loads((ROOT/"artifacts/water-w1/seed-42-r63710000/plan.json").read_text())
    water = load_water_plan(wd, h1, climate, wd["hr_signature"])
    return proof, source, water, PracticalConfig.model_validate(proof["config"])


@pytest.mark.parametrize("total", [0, 1, 121, 10**40+7])
def test_integer_partition_exact_large_and_order_independent_requests(total):
    result = split_integer(total, [1, 7, 13, 4])
    assert sum(result) == total and all(type(x) is int and x >= 0 for x in result)
    assert result == split_integer(total, [1, 7, 13, 4])


def test_leaf_siblings_close_parent_and_vertex_shares_close_leaf(real_inputs):
    proof, _, water, config = real_inputs
    tile = TerrainTile(*proof["allocation"]["tile"])
    parent = tile.parent(tile.level-1)
    children = [TerrainTile(parent.face, tile.level, parent.x*2+x, parent.y*2+y) for y in range(2) for x in range(2)]
    quotas = {c: surface_quota(water, c, config) for c in children}
    node = proof["allocation"]["source_node"]
    original = water.solution.periods[-1]["stores"]["surface"][node]
    expected = _leaf_share(original, parent, water.hydrology.config.level, water.hydrology.radius_m)
    assert sum(q["parcel_quota_liters"] for q in quotas.values()) == expected
    assert all(sum(q["vertex_quota_liters"]) == q["parcel_quota_liters"] for q in quotas.values())
    assert [surface_quota(water, c, config) for c in reversed(children)] == [quotas[c] for c in reversed(children)]
    with pytest.raises(ValueError, match="parent/child"):
        surface_quota(water, parent, config)


@pytest.mark.parametrize("radius", [6_371_000, 63_710_000, 637_100_000, 10**12])
def test_allocation_across_faces_poles_and_extreme_radius(radius):
    from app.game.world.genesis.water_reconciliation.practical.allocation import parcel_level
    config = PracticalConfig()
    # Quantitative fixture only: enormous exact stock; geometry uses real cube charts.
    water = SimpleNamespace(hydrology=SimpleNamespace(radius_m=radius, config=SimpleNamespace(level=2)),
        solution=SimpleNamespace(periods=[{"stores": {"surface": [10**35]*96}}]))
    level = parcel_level(radius, config)
    for face in range(6):
        tile = TerrainTile(face, level, 0, 0)
        peer = tile_neighbor(tile, "west")
        a, b = surface_quota(water, tile, config), surface_quota(water, peer, config)
        assert sum(a["vertex_quota_liters"]) == a["parcel_quota_liters"] > 0
        assert sum(b["vertex_quota_liters"]) == b["parcel_quota_liters"] > 0
        assert a["tile"] != b["tile"]  # Two disjoint dual-area supports, never one duplicate claim.


def test_hydraulic_integer_roots_and_confined_section():
    for n in (0, 1, 8, 1000, 10**90+5):
        root = icbrt(n)
        assert root**3 <= n < (root+1)**3
    section = section_at_depth([1000, 0, 1000], 1000, 500)
    assert section["area_mm2"] == 250000 and section["width_mm"] == 1000
    assert section_at_depth([0, 1000, 0], 1000, 500) is None


def test_real_natural_proof_is_reproducible_without_changing_terrain(real_inputs):
    proof, source, water, config = real_inputs
    terrain = build_terrain_plan(source)
    before = checksum(source.to_dict()), checksum(water.to_dict())
    replay, budget = inspect_parcel(water, TerrainSampler(terrain), TerrainTile(*proof["allocation"]["tile"]), config)
    assert replay == proof
    validate_proof(proof, config, water, terrain.signature)
    assert proof["suggested_transfer_liters"] == 19
    assert proof["capacity"]["required_wetting_liters"] == 11
    assert proof["capacity"]["length_mm"] == 2772
    assert proof["allocation"]["source_node"] == 2717
    assert budget["sample_count"] <= config.max_samples
    assert before == (checksum(source.to_dict()), checksum(water.to_dict()))


def test_tampered_quota_or_capacity_rejected(real_inputs):
    proof, source, water, config = real_inputs
    terrain = build_terrain_plan(source)
    for field in ("allocation", "capacity"):
        bad = deepcopy(proof)
        if field == "allocation":
            bad[field]["vertex_quota_liters"][proof["source_vertex"]] += 1
        else:
            bad[field]["episode_capacity_liters"] += 1
        bad["proof_id"] = checksum({k: v for k, v in bad.items() if k != "proof_id"})[:32]
        with pytest.raises(ValueError):
            validate_proof(bad, config, water, terrain.signature)


def test_future_forcing_has_new_interval_identity_but_no_implicit_credit(real_inputs):
    proof, _, water, config = real_inputs
    tile = TerrainTile(*proof["allocation"]["tile"])
    before = checksum(water.to_dict())
    proposals = [future_forcing_proposal(water, tile, config, cutover_minute=100, cycle=cycle, period=period)
                 for cycle in range(2) for period in range(4)]
    assert len({p["proposal_id"] for p in proposals}) == 8
    for p in proposals:
        assert p["interval_start_minute"] >= 100 and p["interval_end_minute"] > p["interval_start_minute"]
        assert p["precipitation_liters"] == p["rainfall_liters"]+p["snowfall_liters"]
        assert p["credit_authorized"] is p["historical_W1_flux_recredited"] is False
    assert checksum(water.to_dict()) == before
    with pytest.raises(ValueError):
        future_forcing_proposal(water, tile, config, cutover_minute=0, cycle=-1, period=0)


@pytest.mark.parametrize("kwargs", [{"practical_version": True}, {"capacity_version": 2}, {"manning_n_milli": 0}])
def test_policy_versions_and_physical_presets_strict(kwargs):
    with pytest.raises(ValueError):
        PracticalConfig(**kwargs)


def test_shared_interface_aliases_and_model_reproducibility(real_inputs):
    from app.game.world.genesis.water_reconciliation.practical.interface import interface_contract
    from app.game.world.genesis.sphere_topology import face_point
    proof, source, water, config = real_inputs
    a = face_point(0, 8, 3, 8)
    b = face_point(0, 8, 5, 8)
    midpoint = face_point(0, 8, 4, 8)
    peer_midpoint = face_point(2, 0, 4, 8)
    left = interface_contract("test", [a.xyz, b.xyz], midpoint.xyz, 10, 15)
    right = interface_contract("test", [b.xyz, a.xyz], peer_midpoint.xyz, 10, 15)
    assert left == right
    assert left["source_view"]["point"] == left["receiver_view"]["point"]
    assert proof["proof_id"] == "d4194fd1d77749c65f21147b95287eba"


def test_manning_estimate_reduces_with_roughness_and_uncertainty(real_inputs):
    from app.game.world.genesis.water_reconciliation.practical.hydraulics import capacity
    from app.game.world.genesis.sphere_topology import SurfacePoint
    proof, _, water, config = real_inputs
    values = []
    for roughness in (40, 75, 150):
        policy = PracticalConfig(manning_n_milli=roughness, velocity_limit_mm_s=1000)
        result = capacity(proof["cross_sections"], [SurfacePoint(*p) for p in proof["points"]], proof["terrain_profile_mm"],
            5, 203, {"radius_m": water.hydrology.radius_m, "policy": policy})
        values.append(result["q_mm3_s"])
    assert values[0] > values[1] > values[2] > 0
