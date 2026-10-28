from app.db.models.campaign import Campaign
from app.db.models.location import Location, LocationConnection
from app.db.models.region import Region
from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_natural_formations import GenesisFormationCandidate, GenesisLocalWaterBody, GenesisNaturalFormation
from app.game.world.genesis.local_formations import (PROFILE, SUPPORTED, VERSION, _hash, candidate,
                                                      catalog, materialize_for_site, evaluate_context_v2,
                                                      PROFILE_V2, VERSION_V2, candidate_v2)
from app.game.world.genesis.sphere_topology import CellKey, cell_center
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.territory import validate_travel
from app.db.models.world_spatial import LocationSpatialAnchor
from app.schemas.action import ActionRequest


def _address(i):
    return {"face": i % 6, "level": 17, "x": (i // 6) % (2**17), "y": (i * 19) % (2**17)}


def _address_for(seed, archetype):
    for i in range(100_000):
        address = _address(i)
        if candidate(seed, address) == archetype:
            return address
    raise AssertionError(f"No deterministic address found for {archetype}")


def _path_to_archetype(seed, start, archetype, max_steps=30):
    from collections import deque
    from app.game.world.genesis.sphere_topology import DIRECTIONS, neighbor
    queue=deque([start]);parents={start:None}
    while queue:
        key=queue.popleft()
        if candidate(seed,vars(key))==archetype:
            path=[]
            while parents[key] is not None:
                previous,direction=parents[key]
                path.append((key,direction));key=previous
            return list(reversed(path))
        if len(parents)>=(2*max_steps+1)**2:continue
        depth=0;cursor=key
        while parents[cursor] is not None:
            depth+=1;cursor=parents[cursor][0]
        if depth>=max_steps:continue
        for direction in DIRECTIONS:
            next_key=neighbor(key,direction)
            if next_key not in parents:
                parents[next_key]=(key,direction);queue.append(next_key)
    raise AssertionError(f"No {archetype} candidate within {max_steps} local cells")


def test_v24_catalog_identity_and_wgs1_seed_distribution():
    records = catalog()
    assert len(records) == 240
    assert set(SUPPORTED) <= records.keys()
    assert all(records[x]["nivel_fantasia"] != "anomalo" for x in SUPPORTED)
    assert all(records[x]["estado_importacao"] == "proposto_nao_instanciado" for x in SUPPORTED)
    for seed in (42, 0, 7, 2026, 12345):
        outcomes = [candidate(seed, _address(i)) for i in range(10_000)]
        assert outcomes == [candidate(seed, _address(i)) for i in range(10_000)]
        assert set(SUPPORTED) <= set(filter(None, outcomes))
    assert any(candidate(42, _address(i)) != candidate(7, _address(i)) for i in range(500))


def test_formation_action_is_explicit_and_exclusive():
    assert ActionRequest(text="Examinar", formation_action={"kind":"inspect"}).formation_action.kind == "inspect"
    try:
        ActionRequest(text="Examinar", formation_action={"kind":"inspect"}, technique_id="technique")
    except ValueError:
        pass
    else:
        raise AssertionError("Structured formation actions must be exclusive")


def test_new_campaign_profile_is_explicit(client):
    response=client.post("/api/campaigns",json={"name":"WGS1 explícito","world_profile":PROFILE,"world_seed":42})
    assert response.status_code == 200, response.text
    assert response.json()["world_profile"] == PROFILE
    v2=client.post("/api/campaigns",json={"name":"WGS1 v2 explícito","world_profile":PROFILE_V2,"world_seed":42})
    assert v2.status_code == 200, v2.text
    assert v2.json()["world_profile"] == PROFILE_V2
    multicell=client.post("/api/campaigns",json={"name":"WGS2.2 profile",
        "world_profile":"world_genesis_ap1_tp1_wgs2_v2","world_seed":42})
    assert multicell.status_code == 200, multicell.text
    assert multicell.json()["world_profile"] == "world_genesis_ap1_tp1_wgs2_v2"


def test_wgs1_v2_context_rules_explain_hard_blocks_and_preferences():
    land={"physical_inputs":{"T1_height_mm":1200,"T1_slope_ppm":0,"reference_ocean_H1":False,
                             "substrates":[]},
          "logical_facts":{"clima.indice_aridez":0.2},"authority_signature":"e1-test"}
    cave=evaluate_context_v2("EV-LOC-0050",land,0)
    assert not cave["accepted"]
    assert "cave_entrance_lacks_T1_local_relief" in cave["reasons"]
    fantastic=evaluate_context_v2("EV-LOC-0042",land,0)
    assert fantastic["accepted"] and "low_relief_allowed_by_nonmagical_fantastic_exception" in fantastic["reasons"]
    spring=evaluate_context_v2("EV-LOC-0068",land,0)
    assert spring["accepted"] and "dry_region_allowed; explicit local source prevents regional-water inference" in spring["reasons"]
    ocean=evaluate_context_v2("EV-LOC-0036",{**land,"physical_inputs":{**land["physical_inputs"],"reference_ocean_H1":True}},0)
    assert not ocean["accepted"] and ocean["reasons"]==["incompatible_open_ocean_or_subsea_site"]


def test_wgs1_v2_selector_is_versioned_and_repeatable():
    for seed in (42,0,7,2026,12345):
        assert [candidate_v2(seed,_address(i)) for i in range(1000)] == [candidate_v2(seed,_address(i)) for i in range(1000)]
    assert candidate(42,_address(0)) == candidate(42,_address(0))


def test_wgs1_v2_nearby_signal_uses_connected_cell_without_granting_discovery(db_session, monkeypatch):
    from types import SimpleNamespace
    from app.db.models.location import CharacterLocationDiscovery
    from app.game.world.genesis import local_formations
    import app.game.world.genesis.environment.service as environment_service

    campaign=Campaign(name="WGS1 signal",world_seed=42,world_profile=PROFILE_V2,
        playable_state={"natural_formations":{"version":VERSION_V2,
            "signal_policy":local_formations.SIGNAL_POLICY_V2}})
    db_session.add(campaign);db_session.flush()
    region=Region(campaign_id=campaign.id,name="Signal test");db_session.add(region);db_session.flush()
    current_cell=CellKey(**_address(10)); neighbor_cell=CellKey(**_address(11))
    current=Location(region_id=region.id,name="Current",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":vars(current_cell),
            "point":list(cell_center(current_cell).xyz),"prepared":True})
    neighbor=Location(region_id=region.id,name="Unknown area",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":vars(neighbor_cell),
            "point":list(cell_center(neighbor_cell).xyz),"prepared":False})
    db_session.add_all([current,neighbor]);db_session.flush()
    db_session.add(LocationConnection(from_location_id=current.id,to_location_id=neighbor.id,
        direction="norte",distance=1,active=True,spatial_contract={"version":"territory_tp1"}))
    db_session.flush()
    monkeypatch.setattr(local_formations,"candidate_v2",lambda seed,address:"EV-LOC-0050")
    materialized=[]
    monkeypatch.setattr(environment_service,"materialize_environment_point",
        lambda db,cid,point: materialized.append((cid,point)) or object())
    monkeypatch.setattr(local_formations,"materialize_for_site",
        lambda db,campaign,site: SimpleNamespace(archetype_id="EV-LOC-0050"))

    clues=local_formations.nearby_signals(db_session,campaign,current)
    assert clues==["Uma abertura escura na rocha chama a atencao ao norte."]
    assert len(materialized)==1
    assert "EV-LOC-0050" not in clues[0] and "point" not in clues[0]
    assert db_session.query(CharacterLocationDiscovery).count()==0


def test_wgs1_v2_nearby_signal_policy_does_not_activate_in_existing_v2_save(db_session, monkeypatch):
    from app.game.world.genesis.local_formations import nearby_signals
    campaign=Campaign(name="Existing WGS1 v2",world_seed=42,world_profile=PROFILE_V2,
        playable_state={"natural_formations":{"version":VERSION_V2}})
    db_session.add(campaign);db_session.flush()
    region=Region(campaign_id=campaign.id,name="Legacy signal policy");db_session.add(region);db_session.flush()
    site=Location(region_id=region.id,name="Root",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":_address(0),"point":[2**40,0,0],"prepared":True})
    db_session.add(site);db_session.flush()
    assert nearby_signals(db_session,campaign,site)==[]


def test_wgs1_v2_perception_reports_a_signal_before_formation_discovery(db_session, monkeypatch):
    from app.db.models.character import Character
    from app.db.models.location import CharacterLocationDiscovery
    import app.game.perception.service as perception
    import app.game.world.genesis.territory as territory
    import app.game.world.genesis.environment.service as environment_service
    import app.game.world.genesis.local_formations as local_formations

    campaign=Campaign(name="WGS1 signal perception",world_seed=42,world_profile=PROFILE_V2,
        playable_state={"natural_formations":{"version":VERSION_V2,
            "signal_policy":local_formations.SIGNAL_POLICY_V2}})
    db_session.add(campaign);db_session.flush()
    region=Region(campaign_id=campaign.id,name="Signal perception");db_session.add(region);db_session.flush()
    current=Location(region_id=region.id,name="Unknown field",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":_address(20),"point":[2**40,0,0],"prepared":True})
    neighbor=Location(region_id=region.id,name="Unknown area",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":_address(21),"point":[2**40,0,0],"prepared":False})
    db_session.add_all([current,neighbor]);db_session.flush()
    edge=LocationConnection(from_location_id=current.id,to_location_id=neighbor.id,
        direction="norte",distance=1,active=True,spatial_contract={"version":"territory_tp1","metres":1000})
    db_session.add(edge)
    actor=Character(campaign_id=campaign.id,region_id=region.id,location_id=current.id,name="Scout")
    db_session.add(actor);db_session.flush()
    monkeypatch.setattr(territory,"prepare_site",lambda db,location:location)
    monkeypatch.setattr(environment_service,"query_environment",lambda *args,**kwargs:{"baseline":{}})
    monkeypatch.setattr(local_formations,"nearby_signals",lambda *args,**kwargs:[
        "Arcos naturais parecem ligar penhascos ao norte."])
    monkeypatch.setattr(perception,"known_facts",lambda *args,**kwargs:[])

    result=perception.observe_surroundings(db_session,actor)
    assert result.signals==["Arcos naturais parecem ligar penhascos ao norte."]
    assert "EV-LOC-0042" not in " ".join(result.signals)
    assert db_session.query(CharacterLocationDiscovery).filter_by(
        character_id=actor.id,location_id=neighbor.id).count() == 1


def test_wgs1_v2_rejected_neighbor_candidate_skips_repeated_environment_query(db_session, monkeypatch):
    import app.game.world.genesis.environment.service as environment_service
    import app.game.world.genesis.local_formations as local_formations

    campaign=Campaign(name="WGS1 rejected signal",world_seed=42,world_profile=PROFILE_V2,
        playable_state={"natural_formations":{"version":VERSION_V2,
            "signal_policy":local_formations.SIGNAL_POLICY_V2}})
    db_session.add(campaign);db_session.flush()
    region=Region(campaign_id=campaign.id,name="Rejected signal");db_session.add(region);db_session.flush()
    a,b=_address(30),_address(31)
    current=Location(region_id=region.id,name="Current",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":a,"point":list(cell_center(CellKey(**a)).xyz),"prepared":True})
    neighbor=Location(region_id=region.id,name="Neighbor",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":b,"point":list(cell_center(CellKey(**b)).xyz),"prepared":False})
    db_session.add_all([current,neighbor]);db_session.flush()
    db_session.add(LocationConnection(from_location_id=current.id,to_location_id=neighbor.id,
        direction="leste",distance=1,active=True,spatial_contract={"version":"territory_tp1"}))
    key=local_formations.checksum([VERSION_V2,42,b,"EV-LOC-0050"])
    db_session.add(GenesisFormationCandidate(id="rejected-signal-test",campaign_id=campaign.id,
        stable_key=key,archetype_id="EV-LOC-0050",generator_version=VERSION_V2,
        status="rejected",decision={"accepted":False,"reasons":["cave_entrance_lacks_T1_local_relief"]}))
    db_session.flush()
    monkeypatch.setattr(local_formations,"candidate_v2",lambda seed,address:"EV-LOC-0050")
    monkeypatch.setattr(environment_service,"materialize_environment_point",
        lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError("Rejected persisted decisions must not query E1 again")))

    assert local_formations.nearby_signals(db_session,campaign,current)==[]


def test_wgs1_v2_persists_context_decision_and_instance(db_session, monkeypatch):
    import app.game.world.genesis.environment.service as environment_service
    from app.game.world.genesis import local_formations
    world_config=FormationConfigV4().model_dump(mode="json")
    campaign=Campaign(name="WGS1 v2",world_seed=42,world_profile=PROFILE_V2,
        playable_state={"natural_formations":{"version":VERSION_V2,
                        "signal_policy":local_formations.SIGNAL_POLICY_V2},
                        "territory":{"version":"territory_tp1","world_config":world_config}})
    db_session.add(campaign);db_session.flush()
    db_session.add(GenesisWorld(campaign_id=campaign.id,world_seed=42,config=world_config,plan={}));db_session.flush()
    region=Region(campaign_id=campaign.id,name="V2 test region");db_session.add(region);db_session.flush()
    address=next((_address(i) for i in range(1000) if candidate_v2(42,_address(i)) is not None),None)
    assert address is not None
    point=cell_center(CellKey(**address))
    exterior=Location(region_id=region.id,name="TP1 field",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":address,"point":list(point.xyz),"prepared":True})
    db_session.add(exterior);db_session.flush()
    db_session.add(LocationSpatialAnchor(location_id=exterior.id,campaign_id=campaign.id,point=list(point.xyz)))
    db_session.flush()
    facts={"physical_inputs":{"T1_height_mm":1200,"T1_slope_ppm":10000,"reference_ocean_H1":False,"substrates":[]},
        "logical_facts":{"clima.indice_aridez":0.2},"authority_signature":"stable-e1-test"}
    monkeypatch.setattr(environment_service,"query_environment",lambda *args,**kwargs:{"baseline":facts})
    row=local_formations.materialize_for_site(db_session,campaign,exterior)
    assert row and row.generator_version==VERSION_V2
    links=[edge for edge in db_session.query(LocationConnection).all()
        if edge.spatial_contract and edge.spatial_contract.get("formation_id")==row.id]
    assert any(edge.direction=="indício próximo" for edge in links)
    for edge in links:
        validate_travel(db_session,campaign.id,edge)
    coverage=db_session.get(Location,row.location_id).genesis_site["coverage_contract"]
    assert coverage=={"version":"WGS1_COVERAGE_V1","cell_limit":1,"max_horizontal_span_m":700}
    assert row.data["coverage"]["radius_m"]*2<=700
    decision=db_session.query(GenesisFormationCandidate).filter_by(campaign_id=campaign.id).one()
    assert decision.status=="materialized" and decision.decision["accepted"]
    assert decision.decision["policy"]==local_formations.PROFILE_V2_POLICY
    assert local_formations.materialize_for_site(db_session,campaign,exterior).id==row.id
    assert db_session.query(GenesisFormationCandidate).filter_by(campaign_id=campaign.id).count()==1
    rejected_address=next(_address(i) for i in range(1,1000)
        if _address(i)!=address and candidate_v2(42,_address(i)) is not None)
    rejected_point=cell_center(CellKey(**rejected_address))
    rejected_site=Location(region_id=region.id,name="Open-ocean TP1 site",type="genesis_field",
        genesis_site={"version":"territory_tp1","cell":rejected_address,"point":list(rejected_point.xyz),"prepared":True})
    db_session.add(rejected_site);db_session.flush()
    facts["physical_inputs"]["reference_ocean_H1"]=True
    assert local_formations.materialize_for_site(db_session,campaign,rejected_site) is None
    rejected=db_session.query(GenesisFormationCandidate).filter(GenesisFormationCandidate.campaign_id==campaign.id,
        GenesisFormationCandidate.status=="rejected").one()
    assert "incompatible_open_ocean_or_subsea_site" in rejected.decision["reasons"]
    facts["physical_inputs"]["reference_ocean_H1"]=False
    assert local_formations.materialize_for_site(db_session,campaign,rejected_site) is None
    assert db_session.query(GenesisFormationCandidate).filter_by(campaign_id=campaign.id).count()==2


def test_wgs1_http_exploration_cave_water_interaction_and_revisit(client, db_session, monkeypatch):
    from app.db.models.character import Character
    from app.db.models.world_natural_formations import GenesisLocalWaterBody
    from app.game.exploration import service as exploration
    from app.game.world.genesis.sphere_topology import CellKey
    monkeypatch.setattr(exploration,"d20",lambda rng=None:type("Roll",(),{"total":20})())
    campaign=client.post("/api/campaigns",json={"name":"WGS1 HTTP","world_profile":PROFILE,"world_seed":42}).json()
    actor=client.post(f"/api/campaigns/{campaign['id']}/characters",json={"name":"Exploradora"}).json()
    started=client.post(f"/api/campaigns/{campaign['id']}/start",params={"character_id":actor["id"]})
    assert started.status_code == 200, started.text
    state=started.json()["state"]
    assert state["world_profile"] == PROFILE
    stored=db_session.get(Campaign,campaign["id"])
    assert stored.playable_state["natural_formations"]["version"] == VERSION
    root=state["location"]["id"]
    view=client.get(f"/api/campaigns/{campaign['id']}/map-view",params={"character_id":actor["id"]})
    assert view.status_code == 200, view.text
    assert {row["id"] for row in view.json()["locations"]} == {root}

    params={"character_id":actor["id"]};serial=0
    def action(text,formation=None):
        nonlocal serial
        serial+=1
        payload={"text":text,"action_key":f"wgs1-http-{serial}"}
        if formation:payload["formation_action"]={"kind":formation}
        response=client.post(f"/api/campaigns/{campaign['id']}/actions",params=params,json=payload)
        assert response.status_code==200,response.text
        return response.json()

    def refill_test_actor():
        subject=db_session.get(Character,actor["id"])
        subject.stamina_current=subject.stamina_max
        subject.hunger_current=subject.hunger_max
        subject.thirst_current=subject.thirst_max

    explored=action("Exploro os arredores.")
    assert "encontra" in explored["mechanical_summary"]
    root_site=db_session.get(Location,root).genesis_site
    start=CellKey(**root_site["cell"])

    def travel_to(archetype):
        path=_path_to_archetype(42,start,archetype)
        for key,_direction_name in path:
            action("Olho ao redor.")
            current=db_session.get(Character,actor["id"]).location_id
            edge=next((e for e in db_session.query(LocationConnection).filter_by(from_location_id=current,active=True).all()
                       if (db_session.get(Location,e.to_location_id).genesis_site or {}).get("cell")==vars(key)),None)
            assert edge is not None,"the deterministic candidate route must remain traversable"
            refill_test_actor()
            moved=action("Vou para "+edge.direction+".")
            assert moved["state"]["location"]["id"]==edge.to_location_id,moved["mechanical_summary"]
        row=db_session.query(GenesisNaturalFormation).filter_by(campaign_id=campaign["id"],archetype_id=archetype).one()
        return db_session.get(Location,row.location_id),row,path

    water_location,water_formation,water_path=travel_to("EV-LOC-0068")
    action("Olho ao redor.")
    access=db_session.query(LocationConnection).filter_by(from_location_id=db_session.get(Character,actor["id"]).location_id,active=True).filter(
        LocationConnection.to_location_id==water_location.id).one()
    refill_test_actor();entered=action("Vou para "+access.direction+".")
    assert entered["state"]["location"]["id"]==water_location.id
    inspected=action("Inspeciono a nascente.","inspect")
    assert inspected["formation_result"]["water"]["stored_litres"]==12000
    interacted=action("Examino a água.","interact")
    assert "nenhum recurso foi extraído" in interacted["narrative"]
    water_body=db_session.get(GenesisLocalWaterBody,water_formation.id)
    assert water_body.stored_litres==12000 and water_body.revision==0
    action("Olho ao redor.")
    exit_edge=db_session.query(LocationConnection).filter_by(from_location_id=water_location.id,to_location_id=water_location.parent_location_id).one()
    refill_test_actor();action("Vou para "+exit_edge.direction+".")
    action("Olho ao redor.")
    refill_test_actor();action("Vou para "+access.direction+".")
    assert action("Inspeciono novamente.","inspect")["formation_result"]["water"]["stored_litres"]==12000

    # Revisit the same water feature, then return over the same sector path.
    action("Olho ao redor.")
    water_exit=db_session.query(LocationConnection).filter_by(from_location_id=water_location.id,
        to_location_id=water_location.parent_location_id).one()
    refill_test_actor();action("Vou para "+water_exit.direction+".")
    for target_key,_ in [*(reversed(water_path[:-1])),(start,None)]:
        action("Olho ao redor.")
        current=db_session.get(Character,actor["id"]).location_id
        prior=next((e for e in db_session.query(LocationConnection).filter_by(from_location_id=current,active=True).all()
                    if (db_session.get(Location,e.to_location_id).genesis_site or {}).get("cell")==vars(target_key)),None)
        assert prior is not None,"the return route must remain connected"
        refill_test_actor();action("Vou para "+prior.direction+".")
    assert db_session.get(Character,actor["id"]).location_id==root

    cave_location,cave,cave_path=travel_to("EV-LOC-0050")
    action("Olho ao redor.")
    outside=db_session.get(Character,actor["id"]).location_id
    cave_access=db_session.query(LocationConnection).filter_by(from_location_id=outside,active=True).filter(
        LocationConnection.to_location_id==cave_location.id).one()
    refill_test_actor();opened=action("Vou para "+cave_access.direction+".")
    assert opened["state"]["location"]["id"]==cave_location.id
    invalid_entry=action("Entro na galeria interior.")
    assert invalid_entry["state"]["location"]["id"]==cave_location.id
    assert invalid_entry["state"]["location"]["type"]!="genesis_formation_interior"
    action("Olho ao redor.")
    entry=db_session.query(LocationConnection).filter_by(from_location_id=cave_location.id,direction="entrar",active=True).one()
    refill_test_actor();inside=action("Entro na galeria interior.")
    assert inside["state"]["location"]["id"]==cave.data["interior_location_id"]
    cave_inspection=action("Inspeciono o interior.","inspect")
    assert any("cavidade" in feature.lower() for feature in cave_inspection["formation_result"]["features"])
    action("Olho ao redor.")
    refill_test_actor();leave=action("Vou para sair.")
    assert leave["state"]["location"]["id"]==cave_location.id
    again=action("Inspeciono novamente.","inspect")
    assert again["formation_result"]["features"]==cave.data["features"]
    action("Olho ao redor.")
    outer=db_session.query(LocationConnection).filter_by(from_location_id=cave_location.id,
        to_location_id=cave_location.parent_location_id,active=True).one()
    refill_test_actor();assert action("Vou para "+outer.direction+".")["state"]["location"]["id"]==cave_location.parent_location_id
    action("Olho ao redor.")
    revisit=db_session.query(LocationConnection).filter_by(from_location_id=cave_location.parent_location_id,
        to_location_id=cave_location.id,active=True).one()
    refill_test_actor();assert action("Vou para "+revisit.direction+".")["state"]["location"]["id"]==cave_location.id
    assert action("Examino novamente a formação.","inspect")["formation_result"]["features"]==cave.data["features"]
    assert db_session.query(GenesisNaturalFormation).filter_by(campaign_id=campaign["id"],archetype_id="EV-LOC-0050").count()==1


def test_cave_and_water_instances_are_persisted_and_idempotent(db_session):
    db = db_session
    world_config=FormationConfigV4().model_dump(mode="json")
    campaign = Campaign(name="WGS1", world_seed=42, world_profile=PROFILE,
                        playable_state={"natural_formations": {"version": VERSION},
                                        "territory": {"version":"territory_tp1","world_config":world_config}})
    db.add(campaign); db.flush()
    db.add(GenesisWorld(campaign_id=campaign.id, world_seed=42, config=world_config, plan={}))
    region = Region(campaign_id=campaign.id, name="Região de teste")
    db.add(region); db.flush()

    created = {}
    for archetype in SUPPORTED:
        address = _address_for(42, archetype)
        cell = CellKey(**address)
        point = cell_center(cell)
        exterior = Location(region_id=region.id, name="Campo", type="genesis_field",
            genesis_site={"version":"territory_tp1","cell":address,"point":list(point.xyz),"prepared":True})
        db.add(exterior); db.flush()
        db.add(LocationSpatialAnchor(location_id=exterior.id,campaign_id=campaign.id,point=list(point.xyz)))
        row = materialize_for_site(db, campaign, exterior)
        assert row and row.archetype_id == archetype
        created[archetype] = row
        db.flush()
        assert materialize_for_site(db, campaign, exterior).id == row.id
        if archetype == "EV-LOC-0050":assert row.data["interior_location_id"] is not None

    db.commit();db.expire_all()
    created={archetype:db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id,archetype_id=archetype).one()
             for archetype in SUPPORTED}
    cave = created["EV-LOC-0050"]
    interior = db.get(Location, cave.data["interior_location_id"])
    assert interior and interior.parent_location_id == cave.location_id
    links = [row for row in db.query(LocationConnection).all()
             if row.spatial_contract and row.spatial_contract.get("formation_id") == cave.id]
    assert any(row.direction == "entrar" for row in links)
    assert any(row.direction == "sair" for row in links)
    assert any(row.direction == "ind?cio pr?ximo" for row in links)
    for route in links:
        assert route.spatial_contract["metres"] == 10
        validate_travel(db,campaign.id,route)
    water_formation = created["EV-LOC-0068"]
    body = db.get(GenesisLocalWaterBody, water_formation.id)
    assert body and 0 < body.stored_litres <= body.capacity_litres
    assert body.source_origin.startswith(f"{VERSION}:generated_local_spring:")
    assert db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id).count() == len(SUPPORTED)
    from app.game.world.reset import delete_campaign
    assert delete_campaign(db,campaign.id)
    assert db.query(GenesisNaturalFormation).filter_by(campaign_id=campaign.id).count() == 0
    assert db.query(GenesisLocalWaterBody).filter_by(campaign_id=campaign.id).count() == 0


def test_equal_seed_campaigns_share_canonical_site_but_not_gameplay_state(db_session):
    db=db_session;config=FormationConfigV4().model_dump(mode="json")
    address=_address_for(42,"EV-LOC-0068");point=cell_center(CellKey(**address));created=[]
    for label in ("A","B"):
        campaign=Campaign(name="same seed "+label,world_seed=42,world_profile=PROFILE,
            playable_state={"natural_formations":{"version":VERSION},
                            "territory":{"version":"territory_tp1","world_config":config}})
        db.add(campaign);db.flush();db.add(GenesisWorld(campaign_id=campaign.id,world_seed=42,config=config,plan={}));db.flush()
        region=Region(campaign_id=campaign.id,name="Shared canonical region");db.add(region);db.flush()
        exterior=Location(region_id=region.id,name="Same physical cell",type="genesis_field",
            genesis_site={"version":"territory_tp1","cell":address,"point":list(point.xyz),"prepared":True})
        db.add(exterior);db.flush()
        row=materialize_for_site(db,campaign,exterior);created.append((campaign,row))
    first_campaign,first=created[0];second_campaign,second=created[1]
    assert first.archetype_id==second.archetype_id=="EV-LOC-0068"
    assert first.id!=second.id and first.stable_key==second.stable_key
    first_water=db.get(GenesisLocalWaterBody,first.id);second_water=db.get(GenesisLocalWaterBody,second.id)
    first_water.stored_litres-=100;first_water.revision+=1;db.flush()
    assert second_water.stored_litres==12000 and second_water.revision==0


def test_wgs1_migration_adds_tables_without_converting_old_campaign(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text
    from app.core.config import get_settings

    path=tmp_path/"wgs1-compatibility.sqlite"
    url=f"sqlite:///{path.as_posix()}"
    backend=Path(__file__).parents[2]
    monkeypatch.setenv("DATABASE_URL",url)
    get_settings.cache_clear()
    cfg=Config(str(backend/"alembic.ini"));cfg.set_main_option("script_location",str(backend/"alembic"))
    try:
        command.upgrade(cfg,"z35_genesis_territory")
        engine=create_engine(url)
        old_state={"profile":"world_genesis_ap1_v1","location_id":"legacy-location"}
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO campaigns (id,name,created_at,world_seed,world_profile,playable_state) VALUES (:id,:name,:created,:seed,:profile,:state)"),
                {"id":"old-ap1","name":"Old AP1","created":"2026-10-01 12:00:00","seed":42,
                 "profile":"world_genesis_ap1_v1","state":json.dumps(old_state)})
        command.upgrade(cfg,"head")
        assert {"genesis_natural_formations","genesis_local_water_bodies","genesis_formation_coverage_cells"} <= set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            row=conn.execute(text("SELECT world_profile,playable_state FROM campaigns WHERE id='old-ap1'")).one()
            assert row.world_profile == "world_genesis_ap1_v1"
            assert json.loads(row.playable_state) == old_state
            assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
        engine.dispose()
    finally:
        get_settings.cache_clear()
