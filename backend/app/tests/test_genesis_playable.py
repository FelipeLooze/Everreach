"""Production bootstrap and public game flow, never proof-script imports."""
import time
from copy import deepcopy
import pytest
from app.db.models.campaign import Campaign
from app.db.models.character import Character
from app.db.models.world_spatial import LocationSpatialAnchor, GenesisSphereSector
from app.db.models.world_vegetation import GenesisPlantIndividual
from app.game.world.genesis.playable import PROFILE, bootstrap
from app.game.time.clock import get_world_time


def test_profile_validation_and_legacy_default(client, db_session):
    assert client.post('/api/campaigns', json={'name': 'Invalid', 'world_profile': 'invented'}).status_code == 422
    assert client.post('/api/campaigns', json={'name': 'Invalid', 'world_seed': True}).status_code == 422
    c = client.post('/api/campaigns', json={'name': 'Legacy'}).json()
    assert c['world_profile'] == 'legacy'
    assert db_session.get(Campaign, c['id']).playable_state is None


@pytest.mark.parametrize('seed', [42, 8675309])
def test_playable_http_lifecycle(client, db_session, seed):
    timings = {}
    t = time.perf_counter()
    c = client.post('/api/campaigns', json={'name': f'AP1 {seed}', 'world_profile': PROFILE, 'world_seed': seed}).json()
    cid = c['id']; timings['creation'] = time.perf_counter()-t
    a = client.post(f'/api/campaigns/{cid}/characters', json={'name': 'Exploradora'}).json()
    params = {'character_id': a['id']}
    t = time.perf_counter()
    response = client.post(f'/api/campaigns/{cid}/start', params=params)
    assert response.status_code == 200, response.text
    timings['start'] = time.perf_counter()-t
    state = response.json()['state']; assert state['world_profile'] == PROFILE
    campaign = db_session.get(Campaign, cid)
    descriptor = deepcopy(campaign.playable_state)
    assert db_session.get(LocationSpatialAnchor, state['location']['id']) is not None
    assert db_session.query(GenesisSphereSector).filter_by(campaign_id=cid).count() == 1
    # Real, pinned versions rather than defaults or snapshot-only imports.
    from app.game.world.genesis.vegetation import service as vg
    from app.game.world.genesis.climate.service import get_climate_plan
    from app.game.world.genesis.water.service import get_water_plan
    from app.db.models.world_vegetation_lifecycle import GenesisVegetationLife
    from app.db.models.world_vegetation_renewal import GenesisVegetationRenewal
    assert vg.context(db_session, cid).config.vegetation_version == 2
    assert get_climate_plan(db_session, cid).config.land_recycling_ppm == 550000
    assert get_water_plan(db_session, cid).config.source_climate_version == 3
    assert db_session.get(GenesisVegetationLife, cid).descriptor['kind'] == 'vegetation_life_l1_ga1'
    renewal = db_session.get(GenesisVegetationRenewal, cid)
    assert renewal.descriptor['config']['renewal_policy'] == 'adventure_renewal_ga2'
    bootstrap(db_session, campaign)
    assert campaign.playable_state == descriptor
    tools = [i for i in state['inventory']['items'] if i['name'] == 'Tesoura de campo']
    assert len(tools) == 1
    assert tools[0]['equipped_slot'] == 'WAIST'
    assert tools[0]['accessibility'] == 'QUICK'
    def action(key, plant=None, text='Observo a vegetação ao meu redor.'):
        data = {'text': text, 'action_key': key}
        if plant: data['plant_action'] = plant
        r = client.post(f'/api/campaigns/{cid}/actions', params=params, json=data)
        assert r.status_code == 200, r.text
        return r.json()
    t = time.perf_counter(); look = action('first-look'); timings['look'] = time.perf_counter()-t
    plants = look['plant_result']['individuals']; assert plants
    assert all(p['species_id'] is None and p['name'] is None for p in plants)
    target, part = next((p, part) for p in plants for part in p['parts'] if part['available_now'] and part['part'] in ('folhas','fibras','frondes','ramos','talos','tufo'))
    request = {'kind': 'harvest', 'individual_id': target['individual_id'], 'part_id': part['part_id'], 'quantity': 1, 'tool_instance_id': tools[0]['item_instance_id']}
    # Different skills/capabilities may exist nearby; use the explicitly viable initial founder.
    from app.game.world.genesis.playable import FIELD_CAPABILITIES
    sampler = vg.context(db_session, cid)
    eligible = []
    for p in plants:
        row = db_session.get(GenesisPlantIndividual, (cid,p['individual_id']))
        for part in p['parts']:
            canonical = next(k for k in sampler.catalog.species[row.baseline['species_id']].parts() if k['id']==part['part_id'])
            proto=canonical['protocolo_campo_v7']
            if part['available_now'] and proto['dificuldade_base_0_100']<=35 and set(proto['capacidades_necessarias_da_ferramenta'])<=FIELD_CAPABILITIES and any(k.endswith('principal_id') and v=='EV-PROF-BOT-002' for k,v in proto.items()):
                eligible.append((p,part))
    assert eligible
    target,part=eligible[0];request.update(individual_id=target['individual_id'],part_id=part['part_id'])
    t=time.perf_counter();harvest=action('harvest-1',request,'Coleto uma parte.');timings['harvest']=time.perf_counter()-t
    receipt=harvest['plant_result'];assert receipt['quantity']==1 and receipt['exported_mass_mg']>0
    assert 'species_id' not in receipt
    assert any(i['item_instance_id']==receipt['item_instance_id'] for i in harvest['state']['inventory']['items'])
    assert receipt['stock_after'][part['part_id']] == part['remaining']-1
    assert action('harvest-1',request)['plant_result']==receipt
    r=client.post(f'/api/campaigns/{cid}/actions/undo-last',params=params,json={'reason':'Teste de coleta'})
    assert r.status_code==200,r.text
    assert not any(i['item_instance_id']==receipt['item_instance_id'] for i in r.json()['state']['inventory']['items'])
    assert action('observe-undo',{'kind':'observe','individual_id':target['individual_id']})['plant_result']['parts']
    action('harvest-2',request)
    before=get_world_time(db_session,cid).total_minutes()
    action('wait-1',text='Espero 16 horas.')
    assert get_world_time(db_session,cid).total_minutes()==before+16*60
    t=time.perf_counter();revisit=action('revisit',{'kind':'look'});timings['revisit']=time.perf_counter()-t
    assert revisit['plant_result']['individuals']
    db_session.refresh(renewal)
    assert renewal.last_minute == get_world_time(db_session,cid).total_minutes()
    db_session.expire_all()
    resumed=client.post(f'/api/campaigns/{cid}/start',params=params)
    assert resumed.status_code==200,resumed.text
    assert db_session.get(Campaign,cid).playable_state==descriptor
    assert len([i for i in resumed.json()['state']['inventory']['items'] if i['name']=='Tesoura de campo'])==1
    print('AP1_TIMINGS',seed,timings,flush=True)
