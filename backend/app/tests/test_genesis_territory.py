"""TP1 uses production authorities and the normal HTTP action/knowledge flow."""
from copy import deepcopy
from time import perf_counter
import pytest

from app.db.models.campaign import Campaign
from app.db.models.location import Location, LocationConnection
from app.db.models.world_spatial import LocationSpatialAnchor, EntitySpatialCoverage, GenesisSphereSector
from app.db.models.world_vegetation import GenesisPlantIndividual
from app.game.world.genesis.playable import PROFILE
from app.game.world.genesis.territory import prepare_site, validate_travel, route_evidence
from app.game.world.genesis.sphere_topology import CellKey, cell_at, cell_center, neighbor, SurfacePoint
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.sphere_metric import distance_m
from app.game.travel.service import calculate_travel_minutes
from app.game.time.clock import get_world_time


@pytest.mark.parametrize('seed', [42, 8675309])
def test_territory_http_journey(client, db_session, seed, monkeypatch):
    db = db_session
    cid = client.post('/api/campaigns', json={'name': 'TP1', 'world_profile': PROFILE, 'world_seed':seed}).json()['id']
    aid = client.post(f'/api/campaigns/{cid}/characters', json={'name':'Exploradora'}).json()['id']
    params = {'character_id': aid}
    t = perf_counter(); response = client.post(f'/api/campaigns/{cid}/start', params=params)
    assert response.status_code == 200, response.text
    timings = {'start':perf_counter()-t}
    root = response.json()['state']['location']['id']
    visited = [root]
    from app.ai import context_builder as world_context
    from app.game.game_state import build_game_state
    narrator_context=world_context.build_context(db,build_game_state(db,cid,aid),player_input='Olho ao redor.')
    assert 'LOCAL PHYSICAL CONTEXT' in narrator_context
    assert 'Settlement wealth:' not in narrator_context
    assert 'generally considered' not in narrator_context
    journey_sector_keys = {cell_at(SurfacePoint(*db.get(LocationSpatialAnchor,root).point),FormationConfigV4().sector_level)}
    calls = 0
    def action(text, plant=None):
        nonlocal calls
        calls += 1
        body = {'text':text, 'action_key': f'tp1-{calls}'}
        if plant: body['plant_action'] = plant
        r = client.post(f'/api/campaigns/{cid}/actions', params=params, json=body)
        assert r.status_code == 200, r.text
        return r.json()
    def map_view():
        r = client.get(f'/api/campaigns/{cid}/map-view', params=params)
        assert r.status_code == 200, r.text
        return r.json()
    assert {p['id'] for p in map_view()['locations']} == {root}
    assert db.query(Location).count() == 5  # one detailed site, four bounded stubs
    initial = deepcopy(db.get(Location,root).genesis_site)
    # Roll back the same two preparations and repeat in reverse order. The
    # canonical graph/anchors must agree; wall-clock diagnostics are excluded.
    neighbors = [e.to_location_id for e in db.query(LocationConnection).filter_by(from_location_id=root,active=True).order_by(LocationConnection.id).all()][:2]
    versions = []
    for order in (neighbors, list(reversed(neighbors))):
        savepoint = db.begin_nested()
        for lid in order: prepare_site(db,db.get(Location,lid))
        versions.append({
            'anchors': sorted((a.location_id,tuple(a.point)) for a in db.query(LocationSpatialAnchor).all()),
            'routes': sorted((e.id,deepcopy(e.spatial_contract)) for e in db.query(LocationConnection).all()),
            'sites': sorted((l.id,{k:v for k,v in l.genesis_site.items() if k!='preparation_seconds'}) for l in db.query(Location).all())})
        savepoint.rollback(); db.expire_all()
    assert versions[0] == versions[1]
    t=perf_counter(); plants = action('Observo a vegetação.', {'kind':'look'})['plant_result']['individuals']
    timings['plants_root']=perf_counter()-t
    count = db.query(GenesisPlantIndividual).count()
    assert action('Observo a vegetação.', {'kind':'look'})['plant_result']['individuals'] == plants
    assert db.query(GenesisPlantIndividual).count() == count
    root_states = {p['individual_id']: deepcopy(db.get(GenesisPlantIndividual,(cid,p['individual_id'])).state) for p in plants}
    for index in range(2):
        current = visited[-1]
        action('Olho ao redor.')
        assert {p['id'] for p in map_view()['locations']} <= set(visited)
        edges = db.query(LocationConnection).filter_by(from_location_id=current,active=True).order_by(LocationConnection.id).all()
        candidates=[e for e in edges if e.to_location_id not in visited]
        sector_level=FormationConfigV4().sector_level
        current_sector=cell_at(SurfacePoint(*db.get(LocationSpatialAnchor,current).point),sector_level)
        # Exercise a real sector boundary when it is reachable, not just more
        # points inside the already materialized start sector.
        candidates.sort(key=lambda e:cell_at(SurfacePoint(*db.get(LocationSpatialAnchor,e.to_location_id).point),sector_level)==current_sector)
        edge = candidates[0]
        target = edge.to_location_id
        if index == 0:
            from app.db.models.character import Character
            from app.game.travel import service as travel
            actor=db.get(Character,aid)
            stamina=actor.stamina_current; actor.stamina_current=0
            with pytest.raises(travel.TravelError):travel.move_character(db,cid,actor,target)
            assert not db.get(Location,target).genesis_site['prepared']
            actor.stamina_current=stamina
            count_before=db.query(Location).count()
            original_prepare=travel.ensure_location_materialized
            def failure(db, location):
                original_prepare(db,location)
                raise ValueError('injected preparation failure')
            with monkeypatch.context() as patch:
                patch.setattr(travel,'ensure_location_materialized',failure)
                with pytest.raises(travel.TravelError,match='injected'):travel.move_character(db,cid,actor,target)
            assert actor.location_id==current and actor.stamina_current==stamina
            assert db.query(Location).count()==count_before
            assert not db.get(Location,target).genesis_site['prepared']
        before = get_world_time(db,cid).total_minutes()
        expected = calculate_travel_minutes(edge)
        t=perf_counter(); result=action('Vou para '+edge.direction+'.'); timings[f'travel_{index}']=perf_counter()-t
        assert result['state']['location']['id'] == target, result['mechanical_summary']
        assert get_world_time(db,cid).total_minutes() == before+expected
        if index == 0:
            snapshot = deepcopy(db.get(Location,target).genesis_site)
            undo = client.post(f'/api/campaigns/{cid}/actions/undo-last',params=params,json={'reason':'TP1 travel rollback'})
            assert undo.status_code == 200, undo.text
            assert undo.json()['state']['location']['id'] == current
            assert not db.get(Location,target).genesis_site['prepared']
            result = action('Vou para '+edge.direction+'.')
            assert result['state']['location']['id'] == target
            restored = db.get(Location,target).genesis_site
            assert {k:v for k,v in snapshot.items() if k!='preparation_seconds'} == {k:v for k,v in restored.items() if k!='preparation_seconds'}
        assert db.get(Location,target).genesis_site['prepared']
        anchor = db.get(LocationSpatialAnchor,target)
        assert anchor.campaign_id == cid
        assert edge.distance == edge.spatial_contract['metres']/1000
        assert edge.spatial_contract['metres'] >= distance_m(FormationConfigV4(),SurfacePoint(*edge.spatial_contract['from_point']),SurfacePoint(*anchor.point))-0.001
        t=perf_counter(); local=action('Observo a vegetação.',{'kind':'look'}); timings[f'plants_{index}']=perf_counter()-t
        assert not ({p['individual_id'] for p in local['plant_result']['individuals']} & set(root_states))
        visited.append(target)
        journey_sector_keys.add(cell_at(SurfacePoint(*anchor.point),FormationConfigV4().sector_level))
    for target in reversed(visited[:-1]):
        edge=db.query(LocationConnection).filter_by(from_location_id=visited[-1],to_location_id=target).one()
        t=perf_counter(); result=action('Vou para '+edge.direction+'.');timings['return_'+target[-6:]]=perf_counter()-t
        assert result['state']['location']['id']==target
        visited.pop()
    assert db.get(Location,root).genesis_site == initial
    for iid,state in root_states.items():
        assert db.get(GenesisPlantIndividual,(cid,iid)).state == state
    n = db.query(Location).count(); e = db.query(LocationConnection).count()
    prepare_site(db,db.get(Location,root)); prepare_site(db,db.get(Location,root))
    assert (db.query(Location).count(),db.query(LocationConnection).count()) == (n,e)
    assert db.query(EntitySpatialCoverage).count() >= 2
    assert db.query(GenesisSphereSector).filter_by(campaign_id=cid).count() >= len(journey_sector_keys)
    db.expire_all()
    resumed = client.post(f'/api/campaigns/{cid}/start', params=params)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['state']['location']['id'] == root
    assert db.get(Location,root).genesis_site == initial
    edge=db.query(LocationConnection).filter_by(from_location_id=root,active=True).first()
    validate_travel(db,cid,edge)
    original=edge.distance;edge.distance+=1
    with pytest.raises(ValueError,match='cost mismatch'):validate_travel(db,cid,edge)
    edge.distance=original
    with pytest.raises(ValueError):validate_travel(db,'another_campaign',edge)
    print('TP1_TIMINGS',seed,timings, 'locations',n,'edges',e,flush=True)


@pytest.mark.parametrize('radius', [6_371_000,63_710_000,637_100_000])
def test_route_seam_metric_and_physical_barriers(radius):
    config=FormationConfigV4(radius_m=radius)
    from math import ceil,log2
    level=max(FormationConfigV4(radius_m=radius).sector_level,ceil(log2(2*radius/1000)))
    a=CellKey(0,level,2**level-1,2**(level-1))
    b=neighbor(a,'east')
    assert a.face != b.face
    p,q=cell_center(a),cell_center(b)
    flat=lambda _: {'height_mm':100000}
    forward=route_evidence(config,p,q,flat)
    assert forward == route_evidence(config,q,p,flat)
    assert forward['blocked'] is None
    assert forward['metres'] == pytest.approx(distance_m(config,p,q))
    assert len(forward['samples'])<=33
    assert route_evidence(config,p,q,lambda _: {'height_mm':-1000,'reference_ocean_H1':True})['blocked']
    assert route_evidence(config,p,q,lambda _: {'height_mm':-1000,'reference_ocean_H1':False})['blocked'] is None
    assert route_evidence(config,p,q,lambda x: {'height_mm':10000000 if x==q else 100000})['blocked']


def test_existing_ap1_stays_frozen_and_same_seed_is_isolated(client,db_session,monkeypatch):
    from app.game.world.genesis import territory
    db=db_session
    def create():
        c=client.post('/api/campaigns',json={'name':'Isolation','world_profile':PROFILE,'world_seed':42}).json()['id']
        a=client.post(f'/api/campaigns/{c}/characters',json={'name':'Exploradora'}).json()['id']
        r=client.post(f'/api/campaigns/{c}/start',params={'character_id':a})
        assert r.status_code==200,r.text
        return c,a,r.json()['state']['location']['id']
    # Execute the old AP1 bootstrap path with no TP1 hook.
    with monkeypatch.context() as patch:
        patch.setattr(territory,'initialize_territory',lambda *args:None)
        old,actor,origin=create()
    descriptor=deepcopy(db.get(Campaign,old).playable_state)
    old_plants={p.individual_id:deepcopy(p.state) for p in db.query(GenesisPlantIndividual).filter_by(campaign_id=old)}
    new,_,destination=create()
    assert origin != destination
    assert db.get(LocationSpatialAnchor,origin).point==db.get(LocationSpatialAnchor,destination).point
    assert 'territory' not in descriptor
    assert db.get(Location,origin).genesis_site is None
    assert db.query(LocationConnection).filter_by(from_location_id=origin).count()==0
    assert db.get(Location,destination).genesis_site['prepared']
    assert client.post(f'/api/campaigns/{old}/start',params={'character_id':actor}).status_code==200
    assert db.get(Campaign,old).playable_state==descriptor
    assert {p.individual_id:p.state for p in db.query(GenesisPlantIndividual).filter_by(campaign_id=old)}==old_plants
    assert db.query(GenesisPlantIndividual).filter_by(campaign_id=new).count() == len(old_plants)
    edge=db.query(LocationConnection).filter_by(from_location_id=destination,active=True).first()
    with pytest.raises(ValueError):validate_travel(db,old,edge)
