"""WGS2.3.1 controlled order proof; no production selector is changed."""
from copy import deepcopy
import json
from statistics import median
from time import perf_counter

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.campaign import Campaign
from app.db.models.location import CharacterLocationDiscovery, Location, LocationConnection
from app.db.models.region import Region
from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_environment import GenesisEnvironmentPoint
from app.db.models.world_natural_formations import GenesisFormationCandidate, GenesisNaturalFormation
from app.db.models.world_spatial import LocationSpatialAnchor
from app.db.models.world_vegetation import GenesisPlantIndividual, GenesisVegetationCommunity
from app.game.world.genesis import local_formations
from app.game.world.genesis.sphere_topology import CellKey, SurfacePoint, cell_center, cell_at, face_point, neighbor
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.vegetation import service, resources, lifecycle
from app.game.world.genesis.vegetation.config import VegetationConfigV2
from app.game.world.genesis.vegetation.growth_gameplay import LifeConfigGA1
from app.game.world.genesis.vegetation.field import eligibility
from app.game.world.genesis.vegetation.microhabitat import VERSION, ORIGIN_LOOKUP_VERSION, apply_to_environment
from app.game.world.genesis.vegetation.microhabitat_canonical import POLICY, PROFILE, RESOLUTION_VERSION
from app.game.world.genesis.vegetation.renewal_gameplay import initialize_ga2, RenewalConfigGA2
from app.game.world.genesis.vegetation.v2 import VegetationSamplerV2
from scripts.prove_vegetation import prepare
from scripts.validate_vegetation import inputs_vg1


@pytest.fixture(scope="module")
def sources():
    old = inputs_vg1(42)
    return VegetationSamplerV2(old.environment, old.water, VegetationConfigV2(policy=POLICY))


def test_canonical_microhabitat_order_same_point_and_restart(tmp_path, monkeypatch, sources):
    import app.db.models.campaign as campaign_models
    import app.game.world.genesis.wgs2_families as families
    # Identical IDs in two isolated SQLite files permit exact snapshot and
    # signature comparisons, rather than normalizing campaign-scoped IDs.
    monkeypatch.setattr(campaign_models, "generate_id", lambda prefix: prefix + "_order_proof")
    origin = CellKey(2, 17, 2**17-1, 70000)
    affected_cell = neighbor(origin, "east")
    assert affected_cell.face != origin.face
    origin_point = cell_center(origin)
    point = cell_center(affected_cell)
    site_point = local_formations._surface_offset(origin_point, sources.radius, metres=200)
    assert cell_at(site_point, origin.level) == origin
    real = sources.environment.sample(origin_point)
    assert "EV-BIO-SEMIARIDO_ARBUSTIVO" in real["flora_contract"]["eligible_habitat_ids"]
    assert real["physical_inputs"]["reference_ocean_H1"] is False
    record = local_formations.catalog()["EV-LOC-0236"]
    scale = record["geometria"]["escala_horizontal_m_sugerida"]
    maximum = min(3400, int(scale["max"])); minimum = min(maximum, int(scale["min"]))
    original_hash = local_formations._hash
    monkeypatch.setattr(families, "candidate", lambda seed, address, records, **kw:
        "EV-LOC-0236" if seed == 42 and address == vars(origin) else None)
    def controlled_hash(seed, key, label, version=local_formations.VERSION):
        if label == "horizontal_span": return maximum-minimum
        if label == "grau_abrigado": return 2
        return original_hash(seed,key,label,version)
    monkeypatch.setattr(local_formations, "_hash", controlled_hash)
    outcomes = []
    for order in ("formation_first", "vegetation_first"):
        engine = create_engine("sqlite:///" + (tmp_path / (order + ".sqlite")).as_posix())
        event.listen(engine, "connect", enable_sqlite_foreign_keys)
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as db:
            cid = prepare(db, sources)
            campaign = db.get(Campaign, cid); campaign.world_profile = PROFILE
            world = db.get(GenesisWorld, cid)
            region = Region(campaign_id=cid, name="controlled physical site"); db.add(region); db.flush()
            site = Location(region_id=region.id, name="unvisited origin", type="genesis_field",
                genesis_site={"version":"territory_tp1", "cell":vars(origin),
                              "point":list(site_point.xyz), "prepared":False})
            db.add(site); db.flush()
            db.add(LocationSpatialAnchor(location_id=site.id, campaign_id=cid, point=list(site_point.xyz)))
            affected_site = Location(region_id=region.id, name="unvisited covered cell", type="genesis_field",
                genesis_site={"version":"territory_tp1", "cell":vars(affected_cell),
                              "point":list(point.xyz), "prepared":False})
            db.add(affected_site); db.flush()
            db.add(LocationSpatialAnchor(location_id=affected_site.id, campaign_id=cid, point=list(point.xyz)))
            campaign.playable_state = {"natural_formations":{"version":families.VERSION_V2,
                "selection_policy":families.POLICY},
                "microhabitats":{"version":VERSION,"origin_lookup_version":ORIGIN_LOOKUP_VERSION,
                    "canonical_resolution_version":RESOLUTION_VERSION},
                "territory":{"version":"territory_tp1","level":17,"world_config":world.config,
                    "root_cell":vars(origin),"root_point":list(site_point.xyz),"root_region_id":region.id,
                    "root_region_cell":vars(origin.parent(world.config["sector_level"]-3)),
                    "root_location_id":site.id}}
            db.flush()
            resources.initialize_resources(db, cid, experimental=True)
            lifecycle.initialize_life(db, cid, LifeConfigGA1(), experimental=True)
            initialize_ga2(db, cid, RenewalConfigGA2(), experimental=True)
            sampler = service.context(db, cid)
            assert db.query(CharacterLocationDiscovery).count() == 0
            with pytest.raises(ValueError, match="explicit canonical microenvironment"):
                sampler.sample(point)
            if order == "vegetation_first":
                # AP1 probes vegetation before it creates TP1/playable_state.
                pinned_state = deepcopy(campaign.playable_state)
                campaign.playable_state = None
                counts_before = tuple(db.query(model).count() for model in
                    (GenesisNaturalFormation,GenesisEnvironmentPoint,GenesisVegetationCommunity,GenesisPlantIndividual))
                prebootstrap = service.microenvironment_context(db,cid,sampler,point)
                assert tuple(db.query(model).count() for model in
                    (GenesisNaturalFormation,GenesisEnvironmentPoint,GenesisVegetationCommunity,GenesisPlantIndividual)) == counts_before
                campaign.playable_state = pinned_state
                db.flush()
            if order == "formation_first":
                assert local_formations.materialize_for_site(db, campaign, site, _skip_origin_lookup=True)
            else:
                assert db.query(GenesisNaturalFormation).filter_by(campaign_id=cid).count() == 0
            start = perf_counter(); micro = service.microenvironment_context(db,cid,sampler,point)
            lookup_seconds = perf_counter()-start
            assert micro and 0 < micro["modifiers"]["solar_exposure_reduction_ppm"] < 300_000
            comparison = None
            if order == "formation_first":
                # Same persisted formation, point and warmed session: measure
                # the old coverage lookup and canonical validation separately.
                from app.game.world.genesis.vegetation.microhabitat import resolve as coverage_resolve
                old_times=[]; new_times=[]
                for _ in range(10):
                    start=perf_counter(); old_context=coverage_resolve(db,cid,point); old_times.append(perf_counter()-start)
                    start=perf_counter(); new_context=service.microenvironment_context(db,cid,sampler,point); new_times.append(perf_counter()-start)
                    assert old_context == new_context == micro
                from types import SimpleNamespace
                db.info[("L2_batch",cid)] = SimpleNamespace()
                db.info[("L2_advancing",cid)] = True
                batch_times=[]
                try:
                    for _ in range(10):
                        start=perf_counter(); batch_context=service.microenvironment_context(db,cid,sampler,point)
                        batch_times.append(perf_counter()-start)
                        assert batch_context == micro
                finally:
                    db.info.pop(("L2_batch",cid));db.info.pop(("L2_advancing",cid))
                comparison={"coverage_lookup_median_ms":median(old_times)*1000,
                    "canonical_lookup_median_ms":median(new_times)*1000,
                    "canonical_batch_lookup_median_ms":median(batch_times)*1000}
            if order == "vegetation_first":
                assert prebootstrap == micro
            preview = service.sample_initial_community(db,cid,sampler,point)
            assert preview["microenvironment_context"] == micro
            regional_community = sampler.sample(point,microenvironment=None)
            regional = sampler.environment.sample(point)
            local = apply_to_environment(regional, micro)
            regional_ratio = regional["logical_facts"]["clima.indice_aridez"]
            local_ratio = local["logical_facts"]["clima.indice_aridez"]
            pet_reduction = micro["modifiers"]["solar_exposure_reduction_ppm"]*400_000//1_000_000
            assert local_ratio == pytest.approx(regional_ratio * 1_000_000/(1_000_000-pet_reduction))
            assert local["physical_inputs"] == regional["physical_inputs"]
            species = sampler.catalog.species["EV-FL-1506"]
            water = sampler.water_facts(point)
            regional_status = eligibility(species,regional,water)[0]
            local_status = eligibility(species,local,water)[0]
            start = perf_counter(); community = service.materialize_community(db,cid,point,_sampler=sampler)
            community_seconds = perf_counter()-start
            if order == "vegetation_first":
                assert db.query(GenesisNaturalFormation).filter_by(campaign_id=cid).count() == 0
            assert community.baseline["microenvironment_context"] == micro
            assert preview["populations"] == community.baseline["populations"]
            individual = None; selected_slot = None
            for population in community.baseline["populations"]:
                for slot in range(min(population["founder_count"], 64)):
                    try:
                        candidate = service._individual_baseline(sampler,community,population["species_id"],slot,
                            _micro_lookup=lambda q:service.microenvironment_context(db,cid,sampler,q))
                    except ValueError as exc:
                        if "microsite unsupported" not in str(exc): raise
                        continue
                    if candidate["microenvironment_context"] is None:
                        continue
                    individual = service.materialize_individual(db,cid,point,population["species_id"],slot,
                        _sampler=sampler,_community=community)
                    selected_slot = slot
                    break
                if individual is not None: break
            assert individual is not None
            assert individual.baseline["microenvironment_context"] is not None
            # B is processed through the real WGS2 lookup; in vegetation-first
            # it discovers only the physical origin, without preparing TP1 A.
            assert local_formations.materialize_for_site(db,campaign,affected_site)
            assert site.genesis_site["prepared"] is False
            assert service.microenvironment_context(db,cid,sampler,point) == micro
            formation = db.query(GenesisNaturalFormation).filter_by(campaign_id=cid).one()
            assert formation.stable_key == micro["canonical_id"]
            assert formation.data["microenvironment"]["signature"] == micro["contract_signature"]
            route = db.query(LocationConnection).filter_by(from_location_id=site.id,
                to_location_id=formation.location_id).one()
            from app.game.world.genesis.territory import validate_travel
            validate_travel(db, cid, route)
            assert route.spatial_contract["distance_m"] > 100
            assert db.query(CharacterLocationDiscovery).count() == 0
            before = (deepcopy(community.baseline), deepcopy(individual.baseline), deepcopy(individual.state),
                      micro, formation.stable_key, formation.data["microenvironment"]["signature"])
            iid, sid = individual.individual_id, individual.baseline["species_id"]
            assert service.materialize_individual(db,cid,point,sid,selected_slot,_sampler=sampler).individual_id == iid
            assert db.query(GenesisPlantIndividual).filter_by(campaign_id=cid,individual_id=iid).count() == 1
            expected_state = deepcopy(individual.state)
            if order == "vegetation_first":
                # A real R1 removal at the same world minute is not undone by
                # resolving the formation or revisiting the community.
                from scripts.validate_plant_resources import prepare_operator
                actor, tool = prepare_operator(db,cid,individual,sampler)
                service.remove_individual(db,cid,actor.id,iid,tool.id,"wgs231-removal")
                expected_state = deepcopy(individual.state)
                assert expected_state["alive"] is False
                assert service.materialize_community(db,cid,point,_sampler=sampler).baseline == before[0]
                assert service.materialize_individual(db,cid,point,sid,selected_slot,_sampler=sampler).state == expected_state
                decision = db.query(GenesisFormationCandidate).filter_by(campaign_id=cid,stable_key=formation.stable_key).one()
                original = deepcopy(decision.decision)
                decision.decision = {**original,"accepted":False}; db.flush()
                with pytest.raises(ValueError,match="candidate differs"):
                    service.microenvironment_context(db,cid,sampler,point)
                assert service.sample_initial_community(db,cid,sampler,point) == before[0]
                decision.decision = original; db.flush()
                from app.game.world.genesis.environment.service import _identifier
                source_e1 = db.get(GenesisEnvironmentPoint,(cid,_identifier(sampler.environment,origin_point)))
                source_e1.changes = {"controlled_test_change": True}; db.flush()
                with pytest.raises(ValueError,match="E1 changes"):
                    service.microenvironment_context(db,cid,sampler,point)
                source_e1.changes = {}; db.flush()
                # Advance the existing GA2 engine with canonical local context;
                # the removed founder remains dead even if future recruitment is possible.
                from app.game.time.clock import advance_world_time
                advance_world_time(db,cid,4*24*60)
                service.query_community(db,cid,point)
                individual = service.materialize_individual(db,cid,point,sid,selected_slot,_sampler=sampler)
                assert individual.state["alive"] is False
                expected_state = deepcopy(individual.state)
            db.commit()
        service._cache.clear()
        with Session(engine) as db:
            sampler = service.context(db,cid)
            again = service.materialize_community(db,cid,point,_sampler=sampler)
            plant = service.materialize_individual(db,cid,point,sid,selected_slot,_sampler=sampler)
            assert (again.baseline,plant.baseline,plant.state) == (before[0],before[1],expected_state)
            assert service.microenvironment_context(db,cid,sampler,point) == before[3]
            assert db.query(GenesisPlantIndividual).filter_by(campaign_id=cid,individual_id=iid).count() == 1
        engine.dispose()
        outcomes.append(before)
        print(json.dumps({"order":order,"canonical_id":micro["canonical_id"],
            "contract_signature":micro["contract_signature"],"community_checksum":checksum(before[0]),
            "local_environment_signature":before[0]["local_environment_signature"],
            "individual_baseline_checksum":checksum(before[1]),
            "origin_cell":vars(origin),"affected_cell":vars(affected_cell),
            "solar_reduction_ppm":micro["modifiers"]["solar_exposure_reduction_ppm"],
            "individual_id":iid,"species_id":sid,"lookup_seconds":lookup_seconds,
            "community_seconds":community_seconds,"regional_P_PET":regional_ratio,
            "local_P_PET":local_ratio,"species_EV_FL_1506_regional":regional_status,
            "species_EV_FL_1506_local":local_status,
            "regional_cover_ppm":regional_community["cover_ppm"],"local_cover_ppm":preview["cover_ppm"],
            "regional_species":len(regional_community["populations"]),"local_species":len(preview["populations"]),
            "warm_lookup_comparison":comparison}))
    assert outcomes[0] == outcomes[1]


def test_zero_microenvironment_contribution_is_exact_regional_path():
    environment = {"logical_facts":{"clima.indice_aridez":0.14}}
    assert apply_to_environment(environment, {"modifiers":{"solar_exposure_reduction_ppm":0}}) is environment


def test_previous_profile_keeps_persisted_coverage_only(db_session):
    from types import SimpleNamespace
    from app.game.world.genesis.formation_v4 import FormationConfigV4
    from app.schemas.campaign import CampaignCreateRequest
    campaign=Campaign(name="legacy V3",world_seed=42,world_profile="world_genesis_ap1_tp1_wgs2_v3",
        playable_state={"microhabitats":{"version":VERSION},
            "territory":{"level":17,"world_config":FormationConfigV4().model_dump(mode="json")}})
    db_session.add(campaign); db_session.flush()
    sampler=SimpleNamespace(config=SimpleNamespace(policy="regional_canopy_wgs2_microhabitat_v1"))
    assert service.microenvironment_context(db_session,campaign.id,sampler,SurfacePoint(1,0,0)) is None
    older=Campaign(name="legacy V2",world_seed=42,world_profile="world_genesis_ap1_tp1_wgs2_v2")
    db_session.add(older);db_session.flush()
    regional_sampler=SimpleNamespace(config=SimpleNamespace(policy="regional_canopy_v2"))
    assert service.microenvironment_context(db_session,older.id,regional_sampler,SurfacePoint(1,0,0)) is None
    assert CampaignCreateRequest(name="V4",world_profile=PROFILE,world_seed=42).world_profile == PROFILE


def test_unseen_canonical_influence_only_exposes_shade(db_session, monkeypatch):
    from app.game.character.service import create_character
    from app.game.perception.service import observe_surroundings
    import app.game.world.genesis.territory as territory
    import app.game.world.genesis.environment.service as environment_service
    campaign=Campaign(name="privacy",world_seed=42,world_profile=PROFILE)
    db_session.add(campaign);db_session.flush()
    region=Region(campaign_id=campaign.id,name="field");db_session.add(region);db_session.flush()
    site=Location(region_id=region.id,name="field",type="genesis_field",
        genesis_site={"version":"territory_tp1","point":[1,0,0],"prepared":True})
    db_session.add(site);db_session.flush()
    actor=create_character(db_session,campaign.id,"Explorer",None,None)
    actor.region_id=region.id;actor.location_id=site.id;db_session.flush()
    monkeypatch.setattr(territory,"prepare_site",lambda db,location:location)
    monkeypatch.setattr(environment_service,"query_environment",lambda *a,**kw:{})
    monkeypatch.setattr(local_formations,"nearby_signals",lambda *a,**kw:[])
    monkeypatch.setattr(service,"context",lambda *a:object())
    monkeypatch.setattr(service,"microenvironment_context",lambda *a:{"features":["reduced_solar_exposure"],
        "canonical_id":"secret-formation", "formation_id":"secret-instance"})
    observed=observe_surroundings(db_session,actor)
    public=" ".join(observed.features+observed.signals)
    assert "sombra local" in public.lower()
    assert "secret" not in public and "depressão" not in public.lower()
    assert db_session.query(CharacterLocationDiscovery).filter_by(character_id=actor.id).count() == 0


def test_canonical_candidates_cross_face_and_are_campaign_isolated(db_session, monkeypatch):
    from types import SimpleNamespace
    from app.game.world.genesis.formation_v4 import FormationConfigV4
    from app.game.world.genesis.sphere_metric import distance_m
    from app.game.world.genesis.vegetation import microhabitat_canonical as canonical
    import app.game.world.genesis.wgs2_families as families
    config = FormationConfigV4()
    origin = CellKey(0, 17, 2**17-1, 65536)
    point = face_point(2, 1, 8*origin.y+4, 8*2**17)
    assert cell_at(point, 17).face == 2
    assert distance_m(config, point, cell_center(origin)) < 623
    monkeypatch.setattr(families, "candidate", lambda seed, address, records, **kw:
        "EV-LOC-0236" if address == vars(origin) else None)
    original_hash = local_formations._hash
    record = local_formations.catalog()["EV-LOC-0236"]
    scale = record["geometria"]["escala_horizontal_m_sugerida"]
    maximum = min(3400,int(scale["max"])); minimum = min(maximum,int(scale["min"]))
    monkeypatch.setattr(local_formations,"_hash",lambda seed,key,label,version=local_formations.VERSION:
        maximum-minimum if label == "horizontal_span" else 2 if label == "grau_abrigado" else original_hash(seed,key,label,version))
    facts = {"authority_signature":"controlled-e1", "physical_inputs":{
        "T1_height_mm":1000,"T1_slope_ppm":10000,"reference_ocean_H1":False,"JR1_checksum":"controlled-jr1"},
        "logical_facts":{"clima.indice_aridez":0.14},
        "flora_contract":{"eligible_habitat_ids":["EV-BIO-SEMIARIDO_ARBUSTIVO"]}}
    baseline_calls=[]
    def baseline(*args):
        baseline_calls.append(1)
        return SimpleNamespace(baseline=facts,baseline_checksum=checksum(facts))
    monkeypatch.setattr(canonical,"_baseline",baseline)
    environment = SimpleNamespace(signature="same-world",regional=SimpleNamespace(terrain=SimpleNamespace(
        plan=SimpleNamespace(source=SimpleNamespace(config=config)))))
    sampler = SimpleNamespace(config=SimpleNamespace(policy=POLICY),environment=environment)
    a=Campaign(id="canonical-a",name="a",world_seed=42,world_profile=PROFILE)
    b=Campaign(id="canonical-b",name="b",world_seed=42,world_profile=PROFILE)
    db_session.add_all([a,b]); db_session.flush()
    local_a=canonical.resolve(db_session,a.id,point,sampler)
    local_b=canonical.resolve(db_session,b.id,point,sampler)
    assert local_a and local_b and local_a["canonical_id"] == local_b["canonical_id"]
    assert local_a["formation_id"] != local_b["formation_id"]
    assert local_a["contract_signature"] != local_b["contract_signature"]
    assert canonical.resolve(db_session,a.id,point,sampler) == local_a
    assert db_session.query(GenesisNaturalFormation).count() == 0
    runtime = SimpleNamespace()
    db_session.info[("L2_batch",a.id)] = runtime
    db_session.info[("L2_advancing",a.id)] = True
    calls_before = len(baseline_calls)
    assert canonical.resolve(db_session,a.id,point,sampler) == local_a
    assert canonical.resolve(db_session,a.id,point,sampler) == local_a
    assert len(baseline_calls) == calls_before+1
    db_session.info.pop(("L2_batch",a.id));db_session.info.pop(("L2_advancing",a.id))
    assert canonical.resolve(db_session,a.id,point,sampler) == local_a
    assert len(baseline_calls) == calls_before+2
    far = local_formations._surface_offset(point,config.radius_m,metres=5000)
    assert canonical.resolve(db_session,a.id,far,sampler) is None
