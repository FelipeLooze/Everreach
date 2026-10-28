from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.tests.test_genesis_hydro_geometry import foundation, AnalyticFixture, request
from app.game.world.genesis.hydrology.geometry import geometry
from app.game.world.genesis.terrain.address import tile_at, level_for_spacing
from app.game.world.genesis.hydro_geometry.geometry import build_geometry
from app.game.world.genesis.water_reconciliation.coast import CoastRequest, connection_evidence


def fixture():
    source, h1, terrain, plan = foundation.__wrapped__()
    node = next(i for i, z in enumerate(h1.heights) if z < h1.sea_level_m and source.component_at(geometry(2).points[i]).kind == "water_body")
    tile = tile_at(geometry(2).points[node], level_for_spacing(h1.radius_m, 2, 8))
    data = build_geometry(plan, AnalyticFixture(terrain, tile, lambda x, y: -10000-x*1000), request(tile))
    route = data["routes"][0]
    end = next(a for a in data["request"]["anchors"] if a["role"] == "outlet")["point"]
    from app.game.world.genesis.sphere_topology import SurfacePoint
    component = source.component_at(SurfacePoint(*end)).id
    req = CoastRequest(g1_keys=["g1-fixture"], route_ids=[route["id"]], reference_point=end, reference_component_id=component)
    return source, SimpleNamespace(hydrology=h1), data, req


def test_sampled_reference_connection_is_not_export_authorization():
    source, water, data, req = fixture()
    result = connection_evidence(req, {"g1-fixture": data}, {"g1-fixture": "current"}, source, water, 2, [req.reference_component_id])
    assert result["status"] == "sampled_connection_to_reference_verified"
    assert result["export_authorized"] is False
    unregistered = connection_evidence(req, {"g1-fixture": data}, {"g1-fixture": "current"}, source, water, 2)
    assert "ocean_reference_not_explicitly_designated" in unregistered["reasons"]


@pytest.mark.parametrize("problem,reason", [("barrier", "coastal_path_has_T1_land_barrier"),
    ("dry_patch", "reference_open_wet_patch_not_verified"), ("events", "coastal_evidence_events_invalidated"),
    ("resolution", "coastal_resolution_pending")])
def test_coastal_failures_stay_pending(problem, reason):
    source, water, data, req = fixture()
    data = deepcopy(data)
    status = "current"
    if problem == "barrier":
        data["routes"][0]["terrain_profile_mm"][1] = 1
    elif problem == "dry_patch":
        data["graph"]["heights_mm"][0] = 1
    elif problem == "events":
        status = "invalidated"
    else:
        data["routes"][0]["max_probe_spacing_mm"] = 100000
    result = connection_evidence(req, {"g1-fixture": data}, {"g1-fixture": status}, source, water, 2, [req.reference_component_id])
    assert result["status"] == "pending" and reason in result["reasons"]
    assert not result["export_authorized"]
