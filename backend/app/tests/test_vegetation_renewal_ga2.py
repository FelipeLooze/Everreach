from copy import deepcopy
from dataclasses import replace
import json

import pytest
from sqlalchemy.orm import Session
from app.game.time.clock import advance_world_time
from app.game.world.genesis.vegetation import renewal as l2,lifecycle as life,service,sexual
from app.game.world.genesis.vegetation.renewal_gameplay import (
    RenewalConfigGA2,initialize_ga2,configure_profile,checked_record,materialize_child,stage_record,
)
from app.game.world.genesis.vegetation.growth_gameplay import LifeConfigGA1
from app.game.world.genesis.vegetation.life_math import DAY,YEAR,Q
from app.game.world.genesis.vegetation.catalog import load_flora_catalog
from app.game.world.genesis.vegetation.recovery_structure import measure_community
from app.tests.test_vegetation_renewal_l2 import clone_engine
from scripts.validate_plant_resources import inputs
from scripts.validate_adventure_renewal import setup


@pytest.fixture(scope='module')
def sampler():return inputs(42)


def disturbed(db,v,kind='large_tree',config=None):
    cid,point,parent=setup(db,v,42,kind,'GA2',config)
    c=db.get(l2.Community,(cid,parent.community_id));sid=parent.baseline['species_id']
    pop=next(p for p in c.baseline['populations'] if p['species_id']==sid)
    l2.disturb_population(db,cid,c.community_id,sid,700 if kind=='large_tree' else min(150,pop['founder_count']//2),'ga2-review-logging',experimental=True)
    return cid,c,sid,pop


def authoritative(db,cid):
    db.flush()
    return {'native':{r.population_id:r.data for r in db.query(l2.Population).filter_by(campaign_id=cid)},
            'renewing':{r.population_id:r.data for r in db.query(l2.Renewing).filter_by(campaign_id=cid)},
            'events':{r.event_id:(r.status,r.due_minute,r.payload) for r in db.query(l2.Event).filter_by(campaign_id=cid)},
            'bodies':{r.individual_id:(r.baseline,r.state) for r in db.query(l2.Individual).filter_by(campaign_id=cid)},
            'frontier':db.get(l2.Plan,cid).last_minute}


def test_real_catalog_routes_and_bounded_rarity_cadence():
    cat=load_flora_catalog();cfg=RenewalConfigGA2();counts={'authorized':0,'blocked':0}
    for sp in cat.species.values():
        p=configure_profile(l2.reproductive_profile(sp,100),sp,LifeConfigGA1(),cfg)
        allowed=not p['blocked_reason'] or (p['blocked_reason']=='pollination_or_vector_or_propagule_mechanism_unconfirmed' and sexual.authorization(sp)[0])
        counts['authorized' if allowed else 'blocked']+=1
        if sp.magic!='excepcional':
            assert 3*DAY<=p['opportunity_interval_minutes']<=15*DAY
            other=replace(sp,rarity_name='muito_raro')
            p2=configure_profile(l2.reproductive_profile(other,100),other,LifeConfigGA1(),cfg)
            assert p2['opportunity_interval_minutes']==p['opportunity_interval_minutes']
        assert p['inventory_item_id'] is None
    assert counts=={'authorized':2930,'blocked':166}
    with pytest.raises(ValueError):RenewalConfigGA2(intervals_days={'tree':[0,2]})
    with pytest.raises(ValueError):RenewalConfigGA2(annual_packets_per_adult={'tree':1000})
    with pytest.raises(ValueError):l2.parse_config({'renewal_policy':'unknown'})
    with pytest.raises(ValueError,match='annual_packets_per_adult'):RenewalConfigGA2(annual_reserve_ppm=2000)


@pytest.mark.parametrize('kind',['flor','erva','graminea','arbusto','tree','large_tree'])
def test_real_classes_birth_in_days_and_keep_sparse_bodies(db_session,sampler,kind):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler,kind);before=db.query(l2.Individual).count()
    advance_world_time(db,cid,30*DAY);q=l2.query_population(db,cid,c.community_id,sid)
    assert q['children'] and q['living_count']<=pop['founder_count']
    assert db.query(l2.Individual).count()==before
    p=l2.header(db,cid,sampler);first=q['timings']['first_birth_minute']-p.descriptor['activation_minute']
    assert 0<first<=25*DAY
    if kind=='flor':
        events=[e for e in db.query(l2.Event) if e.payload.get('ga2_signature')]
        assert events and all(e.payload.get('sexual_authorization') for e in events)
        assert all(e.payload['parent_id']!=e.payload['sexual_authorization']['mate_id'] for e in events)


def test_sixty_days_equal_six_ten_day_visits_and_full_authoritative_states(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler);db.commit();engine=clone_engine(db)
    advance_world_time(db,cid,60*DAY);qa=l2.query_population(db,cid,c.community_id,sid);a=authoritative(db,cid)
    with Session(engine) as other:
        for _ in range(6):advance_world_time(other,cid,10*DAY);l2.query_population(other,cid,c.community_id,sid)
        assert l2.query_population(other,cid,c.community_id,sid)==qa
        assert authoritative(other,cid)==a
    engine.dispose()


def test_time_rated_quota_finitude_expiry_and_no_R1_funding(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler)
    before={r.individual_id:deepcopy(r.state) for r in db.query(l2.Individual)}
    advance_world_time(db,cid,180*DAY);q=l2.query_population(db,cid,c.community_id,sid)
    for row in db.query(l2.Renewing):
        l2._check(row);b=row.data.get('ga2_budget')
        if not b:continue
        assert b['earned_tokens']==b['producer_work_ppm_minutes']*row.data['profile']['annual_packets_per_mature_adult']//(YEAR*Q)
        assert row.data['ledger']['produced_packets']<=b['earned_tokens']
        assert 0<=b['remainder']<YEAR*Q
        assert all(bank['remaining']<=bank['produced'] for bank in row.data['bank'])
    assert q['ledger']['expired_mg']>0
    for row in db.query(l2.Individual):assert row.state==before[row.individual_id]


def test_compact_hydration_is_exact_and_does_not_change_population_or_structure(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler)
    advance_world_time(db,cid,60*DAY);before=l2.query_population(db,cid,c.community_id,sid)
    structure=measure_community(db,cid,c.community_id,v=sampler)
    native=db.get(l2.Population,(cid,pop['population_id']));entry=next(e for e in native.data['slots'].values() if e.get('occupant'))
    rec=deepcopy(checked_record(entry));child=materialize_child(db,cid,entry,sampler)
    state=stage_record(rec,life.now(db,cid))
    assert all(child.state['life'][key]==state[key] for key in ('height_cm','maturity','birth_minute'))
    assert child.individual_id==rec['individual_id'] and child.baseline['point']==rec['point']
    assert materialize_child(db,cid,entry,sampler) is child
    assert l2.query_population(db,cid,c.community_id,sid)==before
    assert measure_community(db,cid,c.community_id,v=sampler)==structure
    life.validate(child.baseline,child.state)


def test_extinction_without_any_registered_conspecific_origin_persists(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler)
    sources=list(db.query(l2.Renewing).filter_by(campaign_id=cid,species_id=sid))
    for source in sources:life.clear_population(db,cid,source.community_id,sid,'sterile-'+source.population_id,reason='explicit destruction of every registered dispersal source',experimental=True)
    advance_world_time(db,cid,360*DAY);q=l2.query_population(db,cid,c.community_id,sid)
    assert q['living_count']==0 and not q['children'] and q['bank_packets']==0


def test_full_capacity_never_overfills_or_creates_bodies(db_session,sampler):
    db=db_session;cid,point,parent=setup(db,sampler,42,'flor','GA2');sid=parent.baseline['species_id']
    advance_world_time(db,cid,180*DAY);q=l2.query_population(db,cid,parent.community_id,sid)
    assert q['living_count']==q['capacity'] and not q['children'] and q['ledger']['birth_events']==0
    assert db.query(l2.Individual).count()==1


def test_explicit_policy_and_legacy_authority_cannot_be_reconfigured(db_session,sampler):
    db=db_session;cid,_,parent=setup(db,sampler,42,'flor','L2');sig=l2.header(db,cid,sampler).signature
    with pytest.raises(ValueError,match='Explicit'):initialize_ga2(db,cid)
    with pytest.raises(ValueError,match='reconfigure'):initialize_ga2(db,cid,experimental=True)
    assert l2.header(db,cid,sampler).signature==sig


def test_rollback_restores_frontier_reserves_and_compact_births(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler);db.commit();before=authoritative(db,cid);db.commit()
    advance_world_time(db,cid,30*DAY);l2.query_population(db,cid,c.community_id,sid);db.rollback();db.expire_all()
    assert authoritative(db,cid)==before


def test_compact_corruption_is_rejected(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler);advance_world_time(db,cid,30*DAY)
    l2.query_population(db,cid,c.community_id,sid);native=db.get(l2.Population,(cid,pop['population_id']))
    d=deepcopy(native.data);entry=next(e for e in d['slots'].values() if e.get('occupant'))
    entry['ga2_child']['point']=[1,2,3];life._popwrite(native,d);db.flush()
    with pytest.raises(ValueError,match='corrupted'):l2.query_population(db,cid,c.community_id,sid)


def test_real_recolonization_uses_an_external_persistent_source(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler)
    l2.disturb_population(db,cid,c.community_id,sid,pop['founder_count'],'ga2-clear-target',experimental=True,sterilize_bank=True)
    advance_world_time(db,cid,180*DAY);q=l2.query_population(db,cid,c.community_id,sid)
    assert q['living_count']>0
    births=[e for e in db.query(l2.Event).filter_by(campaign_id=cid,population_id=pop['population_id'],status='established')]
    assert births
    first=min(births,key=lambda e:(e.due_minute,e.event_id))
    assert first.payload['source_account']['population_id']!=pop['population_id']
    # Legitimate immigrants can mature under GA1 and become local parents later.
    by_child={e.payload['child_id']:e for e in births}
    for e in births:
        if e.payload['source_account']['population_id']==pop['population_id']:
            parent=by_child[e.payload['parent_id']]
            assert parent.payload['ga2_child']['mature_minute']<=e.payload['source_account']['produced_minute']


def test_single_mature_flower_cannot_self_reproduce_without_a_mate(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler,'flor')
    # Clear every real source other than the population left with one mature founder.
    for source in list(db.query(l2.Renewing).filter_by(campaign_id=cid,species_id=sid)):
        if source.community_id!=c.community_id:
            life.clear_population(db,cid,source.community_id,sid,'single-source-'+source.population_id,reason='explicit absence of compatible neighbours',experimental=True)
    # Fresh initial disturbance requests are deterministic slot sets; full clearing
    # followed by restoring a founder would be artificial, so select cap-1 directly
    # in a separate pristine campaign instead.
    cid2,_,parent=setup(db,sampler,42,'flor','GA2');sid2=parent.baseline['species_id']
    c2=db.get(l2.Community,(cid2,parent.community_id));p2=next(p for p in c2.baseline['populations'] if p['species_id']==sid2)
    l2.disturb_population(db,cid2,c2.community_id,sid2,p2['founder_count']-1,'one-flower',experimental=True,sterilize_bank=True)
    for source in list(db.query(l2.Renewing).filter_by(campaign_id=cid2,species_id=sid2)):
        if source.community_id!=c2.community_id:
            life.clear_population(db,cid2,source.community_id,sid2,'no-mate-'+source.population_id,reason='explicit destruction of other reproductive sources',experimental=True)
    advance_world_time(db,cid2,90*DAY);q=l2.query_population(db,cid2,c2.community_id,sid2)
    assert q['living_count']==1 and q['ledger']['produced_packets']==0 and not q['children']


def test_full_population_late_registration_reconstructs_the_same_history(db_session,sampler):
    db=db_session;cid,_,parent=setup(db,sampler,42,'large_tree','GA2')
    c=db.get(l2.Community,(cid,parent.community_id))
    pop=next(p for p in c.baseline['populations'] if p['species_id']!=parent.baseline['species_id'] and sampler.catalog.species[p['species_id']].magic!='excepcional')
    sid=pop['species_id'];db.commit();engine=clone_engine(db)
    l2.query_population(db,cid,c.community_id,sid);advance_world_time(db,cid,60*DAY)
    a=l2.query_population(db,cid,c.community_id,sid);state=authoritative(db,cid)
    with Session(engine) as other:
        advance_world_time(other,cid,60*DAY);b=l2.query_population(other,cid,c.community_id,sid)
        assert a==b and authoritative(other,cid)==state
    engine.dispose()


def test_ga2_http_undo_restores_compact_events_and_reserves(client,db_session,sampler):
    from scripts.validate_plant_resources import prepare_operator
    db=db_session;cid,c,sid,pop=disturbed(db,sampler)
    advance_world_time(db,cid,30*DAY);l2.query_population(db,cid,c.community_id,sid)
    native=db.get(l2.Population,(cid,pop['population_id']));entry=next(e for e in native.data['slots'].values() if e.get('occupant'))
    child=materialize_child(db,cid,entry,sampler);actor,tool=prepare_operator(db,cid,child,sampler)
    db.commit();before=authoritative(db,cid);db.commit();minute=life.now(db,cid)
    url=f'/api/campaigns/{cid}/actions';params={'character_id':actor.id}
    body={'text':'Remover muda','action_key':'ga2-undo','plant_action':{'kind':'remove','individual_id':child.individual_id,'tool_instance_id':tool.id}}
    r=client.post(url,params=params,json=body);assert r.status_code==200,r.text
    again=client.post(url,params=params,json=body);assert again.json()==r.json()
    u=client.post(url+'/undo-last',params=params,json={'reason':'desfazer remocao GA2'})
    assert u.status_code==200,u.text
    db.expire_all();assert life.now(db,cid)==minute and authoritative(db,cid)==before


def test_year_round_catalog_activity_is_not_an_off_season():
    from app.game.world.genesis.vegetation.renewal_gameplay import seasonal_rates
    sp=next(iter(load_flora_catalog().species.values()))
    traits=json.loads(sp.growth_json or '{}');traits['estacoes_crescimento_preservadas']=['todo_ano_condicionado_a_atividade_biologica']
    assert seasonal_rates(replace(sp,growth_json=json.dumps(traits)),RenewalConfigGA2())==[Q]*4


def test_corrupt_birth_rolls_back_the_whole_ga2_frontier_and_retry_is_unique(db_session,sampler):
    db=db_session;cid,c,sid,pop=disturbed(db,sampler);advance_world_time(db,cid,DAY)
    l2.query_population(db,cid,c.community_id,sid)
    pending=db.query(l2.Event).filter_by(campaign_id=cid,status='pending').first();assert pending
    event_id=pending.event_id;child_id=pending.payload['child_id'];pending.payload_checksum='corrupt';db.commit()
    frontier=db.get(l2.Plan,cid).last_minute;state=deepcopy(db.get(l2.Renewing,(cid,pop['population_id'])).data)
    advance_world_time(db,cid,7*DAY)
    with pytest.raises(ValueError,match='corrupted'):l2.query_population(db,cid,c.community_id,sid)
    db.expire_all();assert db.get(l2.Plan,cid).last_minute==frontier
    assert db.get(l2.Renewing,(cid,pop['population_id'])).data==state
    assert not any(k[0] in ('L2_batch','L2_advancing') for k in db.info if isinstance(k,tuple))
    e=db.get(l2.Event,(cid,event_id));e.payload_checksum=life.checksum(e.payload);db.flush()
    q=l2.query_population(db,cid,c.community_id,sid)
    assert sum(ch['id']==child_id for ch in q['children'])==1
    assert l2.query_population(db,cid,c.community_id,sid)==q


def test_encounter_hydrates_one_exact_child_and_finite_collection_replays(db_session,sampler):
    from scripts.validate_plant_resources import prepare_operator,set_window
    db=db_session;cid,c,sid,pop=disturbed(db,sampler,'erva');advance_world_time(db,cid,30*DAY)
    before=l2.query_population(db,cid,c.community_id,sid);native=db.get(l2.Population,(cid,pop['population_id']))
    entry=next(e for e in native.data['slots'].values() if e.get('occupant'))
    entry=min((e for e in native.data['slots'].values() if e.get('occupant')),key=lambda e:e['ga2_child']['birth_minute'])
    record=deepcopy(checked_record(entry))
    from app.game.world.genesis.sphere_topology import SurfacePoint
    founder=service.materialize_individual(db,cid,SurfacePoint(*c.baseline['point']),sid,record['slot'])
    assert not founder.state['alive']
    child=life.current_occupant(db,cid,founder,sampler)
    assert child.individual_id==record['individual_id'] and child.baseline['point']==record['point']
    assert l2.query_population(db,cid,c.community_id,sid)==before
    raw={p['id']:p for p in sampler.catalog.species[sid].parts()}
    pid=next(pid for pid,p in child.baseline['resource_profile']['parts'].items() if p['state']=='usable' and p['maturity_required']=='adult')
    part=raw[pid];actor,tool=prepare_operator(db,cid,child,sampler);set_window(db,cid,part,child,sampler)
    # GA2/GA1 do not fabricate winter leaf stock. Use the real catalog window
    # and allow unchanged L1 partial-tissue recovery to elapse before collection.
    advance_world_time(db,cid,14*DAY);life.sync(db,cid,child,sampler)
    assert child.state['part_stock'][pid]>0
    r=service.harvest(db,cid,actor.id,child.individual_id,pid,1,tool.id,'ga2-real-harvest')
    state=deepcopy(child.state)
    assert r['exported_mass_mg']>0
    assert service.harvest(db,cid,actor.id,child.individual_id,pid,1,tool.id,'ga2-real-harvest')==r
    assert child.state==state
    life.validate(child.baseline,child.state)


def test_transaction_cohort_cache_preserves_the_complete_uncached_result(db_session,sampler,monkeypatch):
    from app.game.world.genesis.vegetation.renewal_gameplay import GA2Runtime
    db=db_session;cid,c,sid,pop=disturbed(db,sampler);db.commit();engine=clone_engine(db)
    advance_world_time(db,cid,180*DAY);qa=l2.query_population(db,cid,c.community_id,sid);a=authoritative(db,cid)
    original=GA2Runtime.cohort
    def uncached(self,row,minute):
        self.cohort_cache.clear();self.compact_cache.clear()
        return original(self,row,minute)
    monkeypatch.setattr(GA2Runtime,'cohort',uncached)
    with Session(engine) as other:
        advance_world_time(other,cid,180*DAY)
        assert l2.query_population(other,cid,c.community_id,sid)==qa
        assert authoritative(other,cid)==a
    engine.dispose()


def test_matched_control_removes_exactly_the_same_real_slots_and_replays(db_session,sampler):
    db=db_session
    a,_,parent_a=setup(db,sampler,42,'large_tree','L2')
    b,_,parent_b=setup(db,sampler,42,'large_tree','GA2')
    assert parent_a.community_id==parent_b.community_id and parent_a.baseline['species_id']==parent_b.baseline['species_id']
    cid=parent_a.community_id;sid=parent_a.baseline['species_id']
    receipt=l2.disturb_population(db,a,cid,sid,700,'matched-control',experimental=True)
    slots=receipt.payload['selected_slots']
    r=l2.disturb_population(db,b,cid,sid,700,'matched-control',experimental=True,_selected_slots=slots)
    assert r.payload['selected_slots']==slots
    assert l2.disturb_population(db,b,cid,sid,700,'matched-control',experimental=True,_selected_slots=slots) is r
    na=db.get(l2.Population,(a,receipt.population_id));nb=db.get(l2.Population,(b,r.population_id))
    assert na.data==nb.data
    with pytest.raises(ValueError,match='unique'):
        l2.disturb_population(db,b,cid,sid,2,'bad-slots',experimental=True,_selected_slots=[0,0])
    with pytest.raises(ValueError,match='outside'):
        l2.disturb_population(db,b,cid,sid,1,'outside-slots',experimental=True,_selected_slots=[10**9])


def test_failed_late_registration_is_atomic_and_retry_reconstructs_history(db_session,sampler,monkeypatch):
    from app.game.world.genesis.vegetation.renewal_gameplay import GA2Runtime
    db=db_session;cid,_,parent=setup(db,sampler,42,'large_tree','GA2')
    c=db.get(l2.Community,(cid,parent.community_id))
    pop=next(p for p in c.baseline['populations'] if p['species_id']!=parent.baseline['species_id'] and sampler.catalog.species[p['species_id']].magic!='excepcional')
    sid=pop['species_id'];advance_world_time(db,cid,60*DAY);l2.advance(db,cid,sampler)
    original=GA2Runtime.produce
    def fail(self,row,minute):raise ValueError('injected registration failure')
    monkeypatch.setattr(GA2Runtime,'produce',fail)
    with pytest.raises(ValueError,match='registration failure'):l2.query_population(db,cid,c.community_id,sid)
    assert db.get(l2.Renewing,(cid,pop['population_id'])) is None
    assert not any(k[0]=='GA2_registering' for k in db.info if isinstance(k,tuple))
    monkeypatch.setattr(GA2Runtime,'produce',original)
    q=l2.query_population(db,cid,c.community_id,sid)
    assert q['living_count']==q['capacity'] and q['ledger']['produced_packets']>0
