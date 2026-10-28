from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import pytest
from app.game.world.genesis.geology.catalog import load_catalog
from app.game.world.genesis.geology.config import GeologyConfig
from app.game.world.genesis.geology.field import build_geology_plan, load_geology_plan
from app.game.world.genesis.geology.adapter import adapt_unit, assess_bridge, evaluate_opportunities
from app.game.world.genesis.geology.calibration import select_test_deposits, ExperimentalCalibration, WORLD_CAPS
from app.game.world.genesis.formation_plan import build_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.terrain.field import build_terrain_plan, checksum
from app.game.world.genesis.terrain.address import TerrainTile
from app.game.world.genesis.sphere_topology import SurfacePoint, face_point


@pytest.fixture(scope="module")
def real():
    source = build_plan(42,FormationConfigV4())
    terrain = build_terrain_plan(source)
    return terrain,build_geology_plan(terrain)


def test_catalog_unchanged_and_extension_cardinalities():
    catalog = load_catalog()
    assert len(catalog["materials"]) == 120
    assert len(catalog["bridges"]) == 18
    assert len(catalog["alternatives"]) == 24
    assert len(catalog["substrates"]) == 20
    assert sum(len(m["extracao_e_obtencao"]["perfis_por_contexto"]) for m in catalog["materials"].values()) == 360
    assert all(len(m["propriedades_0_100"]) == 14 for m in catalog["materials"].values())
    catalog["materials"].clear()
    assert len(load_catalog()["materials"]) == 120


def test_real_positive_eligibility_and_causal_history(real):
    terrain,plan = real
    before = checksum(terrain.source.to_dict())
    catalog = load_catalog()
    results = [evaluate_opportunities(adapt_unit(u,plan.signature),catalog) for u in plan.units]
    assert len(plan.units) == 196
    assert sum(len(a["opportunities"]) for a in results) == 652
    assert any(a["bridges"]["veio_montanhoso"]["eligible"] for a in results)
    for unit in plan.units:
        adapt_unit(unit,plan.signature)
        if "circulacao_mineralizante_confirmada" in unit["evidence_records"]:
            assert {"intrusive_thermal_episode","fracture_network","hydrothermal_circulation"} <= {h["kind"] for h in unit["history"]}
        assert unit["present_water_or_ecosystem_inferred"] is False
    assert checksum(terrain.source.to_dict()) == before


def test_roundtrip_determinism_and_no_regeneration(real,monkeypatch):
    terrain,plan = real
    assert build_geology_plan(terrain).to_dict() == plan.to_dict()
    def forbidden(*a,**kw):
        raise AssertionError("Saved geology must not reconstruct history")
    monkeypatch.setattr("app.game.world.genesis.geology.field.reconstruct",forbidden)
    loaded = load_geology_plan(json.loads(json.dumps(plan.to_dict())),terrain)
    assert loaded.to_dict() == plan.to_dict()
    altered = loaded.to_dict()
    altered["units"][0]["substrates"] = ["made-up"]
    with pytest.raises(ValueError):
        load_geology_plan(altered,terrain)


def test_determinism_between_fresh_processes(real):
    _,plan = real
    code = "from app.game.world.genesis.formation_plan import build_plan; from app.game.world.genesis.formation_v4 import FormationConfigV4; from app.game.world.genesis.terrain.field import build_terrain_plan; from app.game.world.genesis.geology.field import build_geology_plan; print(build_geology_plan(build_terrain_plan(build_plan(42,FormationConfigV4()))).data['checksum'])"
    result = subprocess.run([sys.executable,"-c",code],cwd=Path(__file__).resolve().parents[2],
                            capture_output=True,text=True,check=True)
    assert result.stdout.strip() == plan.data["checksum"]


@pytest.mark.parametrize("radius",[6371000,63710000,637100000,1000000000000])
def test_giant_scale_is_bounded_and_has_independent_seed(radius):
    a = build_geology_plan(build_terrain_plan(build_plan(7,FormationConfigV4(radius_m=radius))))
    b = build_geology_plan(build_terrain_plan(build_plan(11,FormationConfigV4(radius_m=radius))))
    assert 2 <= len(a.units) <= 384
    assert len(json.dumps(a.to_dict())) < 2_000_000
    assert a.signature != b.signature
    assert a.units[0]["geological_unit_id"] != b.units[0]["geological_unit_id"]


def test_faces_poles_sector_boundaries_and_lod(real):
    _,plan = real
    # All physical cube edges: compare two incident chart representations.
    from app.game.world.genesis.terrain.address import chart, point_on_face
    from app.game.world.genesis.sphere_topology import BASES
    for face in range(6):
        for x,y in ((0,5),(16,5),(5,0),(5,16),(0,0),(16,16),(8,8)):
            point = face_point(face,x,y,16)
            expected = plan.unit_at(point)["geological_unit_id"]
            for peer,(normal,_,_) in enumerate(BASES):
                if sum(a*b for a,b in zip(normal,point.xyz)) == max(map(abs,point.xyz)):
                    _,u,v,d = chart(point,peer)
                    assert plan.unit_at(point_on_face(peer,u,v,d))["geological_unit_id"] == expected
    for point in (SurfacePoint(0,0,1),SurfacePoint(0,0,-1)):
        assert plan.unit_at(point) == plan.unit_at(SurfacePoint(*(v*1000 for v in point.xyz)))
    # Exact same shared point at three render LODs and two adjacent tiles.
    points = [TerrainTile(0,8,100,120).point(16,8,16),TerrainTile(0,8,101,120).point(0,8,16),
              TerrainTile(0,7,50,60).point(16,8,32)]
    assert len({plan.unit_at(p)["geological_unit_id"] for p in points}) == 1
    ids = [u["geological_unit_id"] for u in plan.units]
    assert [plan.unit_at(SurfacePoint(*u["center"]))["geological_unit_id"] for u in reversed(plan.units)] == list(reversed(ids))


def test_missing_evidence_never_synthesized_and_all_bridges_fail_closed(real):
    _,plan = real
    contract = adapt_unit(plan.units[0],plan.signature)
    contract["evidence_flags"] = []
    catalog = load_catalog()
    assert all(not assess_bridge(contract,b)["eligible"] for b in catalog["bridges"].values())
    assert evaluate_opportunities(contract,catalog)["opportunities"] == []
    broken = deepcopy(plan.units[0])
    broken["evidence_records"]["invented"] = {"authority":"V4","history_kind":"unrecorded"}
    with pytest.raises(ValueError,match="supporting history"):
        adapt_unit(broken,plan.signature)


@pytest.mark.parametrize("route_index",range(24))
def test_all_additive_routes_are_integrated_without_extra_slots(route_index):
    catalog = load_catalog()
    route = catalog["alternatives"][route_index]
    bridge = catalog["bridges"][route["origem_alternativa_modelo_id"]]
    primary = catalog["bridges"][route["origem_principal_v4_preservada"]]
    requirements = [bridge["requisitos"],primary["requisitos"]]
    flags = set(route["evidencias_adicionais_necessarias_all"])
    for r in requirements:
        flags.update(r["evidencias_obrigatorias_all"])
        flags.update(r["evidencias_adicionais_any"])
    # Controlled adapter fixture; never injected into the production demonstration.
    contract = {"world_id":"fixture","geological_unit_id":"fixture-unit","formation_opportunity_id":"fixture-formation",
        "region_id":"fixture-region","lithology_substrate_ids":list(catalog["substrates"]),
        "evidence_flags":list(flags),"event_instance_ids":["fixture-event"],"canonical_authorizations":["fixture-canon"]}
    results = evaluate_opportunities(contract,catalog)["opportunities"]
    actual = [o for o in results if o["material_id"]==route["material_id"]]
    assert len(actual) == 1
    assert route["id"] in {r["route_id"] for r in actual[0]["routes"]}
    without = deepcopy(catalog)
    without["alternatives"] = []
    original = next(o for o in evaluate_opportunities(contract,without)["opportunities"] if o["material_id"]==route["material_id"])
    assert actual[0]["opportunity_id"] == original["opportunity_id"]


def test_calibration_caps_no_legendary_and_order_independent(real):
    _,plan = real
    assert select_test_deposits(plan,ExperimentalCalibration(rate_factor_ppm=0)) == []
    from app.game.world.genesis.geology.field import GeologyPlan
    reversed_plan = GeologyPlan({**plan.data,"units":list(reversed(plan.units))})
    assert select_test_deposits(plan) == select_test_deposits(reversed_plan)
    # Several real seeds to exercise positive and negative proposed sources.
    all_sources = []
    for seed in (0,1,2,3,7):
        p = build_geology_plan(build_terrain_plan(build_plan(seed,FormationConfigV4())))
        selected = select_test_deposits(p)
        counts = Counter(s["material_id"] for s in selected)
        regions = [(s["material_id"],s["region_id"]) for s in selected]
        assert len(regions) == len(set(regions))
        assert all(counts[s["material_id"]] <= WORLD_CAPS[s["rarity"]] and s["rarity"] not in ("lendario","muito_raro") for s in selected)
        all_sources.extend(selected)
    assert all_sources


def test_no_water_or_biological_fallback(real):
    _,plan = real
    catalog = load_catalog()
    for unit in plan.units:
        assessed = evaluate_opportunities(adapt_unit(unit,plan.signature),catalog)
        for model in ("aluvião","biomineral","glacial","litoral","meteoritico","recifal","pantano","evaporito","veio_arcano","veio_anomalo"):
            assert not assessed["bridges"][model]["eligible"]
        assert not set(unit["substrates"]) & {f"EV-GEO-SUB-{n:03d}" for n in range(16,21)}


def test_deep_geometry_requirement_is_reachable_without_altitude():
    plan = build_geology_plan(build_terrain_plan(build_plan(0,FormationConfigV4())))
    deep = [u for u in plan.units if "unidade_geologica_profunda" in u["evidence_records"]]
    assert deep
    assert all(u["burial_proxy_m"] >= 6000 and u["depth_index_0_100"] >= 60 for u in deep)
    assert any(evaluate_opportunities(adapt_unit(u,plan.signature))["bridges"]["veio_profundo"]["eligible"] for u in deep)


@pytest.mark.parametrize("kwargs",[{"geology_version":True},{"geology_version":2},{"expected_provinces":193}])
def test_explicit_versions(kwargs):
    with pytest.raises(ValueError):
        GeologyConfig(**kwargs)
