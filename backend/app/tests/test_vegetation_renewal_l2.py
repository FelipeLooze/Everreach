from copy import deepcopy
import json,sqlite3
import pytest
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db.models.world_vegetation import GenesisPlantIndividual as Individual
from app.db.models.world_vegetation_lifecycle import GenesisVegetationLifeEvent as Event
from app.db.models.world_vegetation_renewal import GenesisRenewingPopulation as Population,GenesisVegetationRenewal as Plan
from app.game.world.genesis.vegetation import service,resources,lifecycle as life,renewal as l2
from app.game.world.genesis.vegetation.life_math import DAY,YEAR
from app.game.world.genesis.vegetation.renewal import RenewalConfigL2
from app.game.time.clock import advance_world_time
from scripts.validate_plant_resources import inputs,actual_individual,candidates
from scripts.prove_vegetation import prepare


@pytest.fixture(scope='module')
def sampler():return inputs(42)


def setup(db,v,seed=42,kind='arvore',config=None):
    cid=prepare(db,v);resources.initialize_resources(db,cid,experimental=True)
    point,ind,part=actual_individual(db,cid,v,seed,kind)
    life.initialize_life(db,cid,experimental=True)
    l2.initialize_renewal(db,cid,config,experimental=True)
    return cid,point,ind,part


def test_profiles_audit_real_strategies_and_no_inventory_species():
    from app.game.world.genesis.vegetation.catalog import load_flora_catalog
    cat=load_flora_catalog();blocked=0;internal=0
    for sp in cat.species.values():
        p=l2.reproductive_profile(sp,100)
        assert p['inventory_item_id'] is None and p['canonical_collectable_part_id'] is None
        assert 4*p['packets_per_adult_per_period']*p['unit_mass_mg']<=p['annual_modeled_reserve_per_adult_mg']
        if 'poliniza' in p['canonical_strategy'] or sp.magic=='excepcional':assert p['blocked_reason']
        if p['blocked_reason']:blocked+=1
        else:internal+=1
    assert internal>0 and blocked>0 and internal+blocked==3096
    with pytest.raises(ValueError):RenewalConfigL2(renewal_version=True)


def test_full_population_produces_finite_bank_without_death(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler)
    capacity=next(x['founder_count'] for x in sampler.sample(point)['populations'] if x['species_id']==ind.baseline['species_id'])
    advance_world_time(db,cid,2*YEAR)
    q=l2.query_population(db,cid,ind.community_id,ind.baseline['species_id'])
    assert q['living_count']==capacity and q['ledger']['produced_packets']>0 and q['ledger']['expired_mg']>0
    assert q['ledger']['birth_events']==0 and not q['children'] and q['bank_packets']<=4*capacity


def test_seven_hundred_tree_losses_recover_as_new_age_cohorts(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler);sid=ind.baseline['species_id']
    r=l2.disturb_population(db,cid,ind.community_id,sid,700,'seven-hundred',experimental=True)
    assert len(r.payload['selected_slots'])==700
    initial=l2.query_population(db,cid,ind.community_id,sid);assert initial['capacity']==1037 and initial['living_count']==337
    advance_world_time(db,cid,10*YEAR);q=l2.query_population(db,cid,ind.community_id,sid)
    assert 337<q['living_count']<=1037 and q['stages']['young']>0
    assert len({c['birth_minute'] for c in q['children']})>2
    assert all(c['id'].startswith('vgi:l2:') for c in q['children'])
    assert any(c['height_cm']<ind.baseline['height_cm'] for c in q['children'])
    for row in db.query(Population):l2._check(row)
    removed=set(r.payload['selected_slots'])
    assert all(not plant.state['alive'] for plant in db.query(Individual) if plant.baseline.get('birth_event_id') is None and plant.baseline['species_id']==sid and plant.baseline['slot'] in removed)


def clone_engine(db):
    engine=create_engine('sqlite:///:memory:');raw=engine.raw_connection();source=db.get_bind().raw_connection()
    source.driver_connection.backup(raw.driver_connection);source.close();raw.close();return engine


def snapshot(db,cid,c,sid):
    q=l2.query_population(db,cid,c,sid)
    return {'query':q,'populations':{r.population_id:r.data for r in db.query(Population).filter_by(campaign_id=cid)},
        'events':{r.event_id:(r.status,r.payload,r.due_minute) for r in db.query(Event).filter_by(campaign_id=cid)},
        'individuals':{r.individual_id:(r.baseline,r.state) for r in db.query(Individual).filter_by(campaign_id=cid)}}


def test_continuous_vs_seasonal_visits_are_identical(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler);sid=ind.baseline['species_id']
    l2.disturb_population(db,cid,ind.community_id,sid,120,'chunk-proof',experimental=True);db.commit();engine=clone_engine(db)
    advance_world_time(db,cid,3*YEAR);a=snapshot(db,cid,ind.community_id,sid)
    with Session(engine) as other:
        for days in (7,23,60,90,180,360,360):
            advance_world_time(other,cid,days*DAY);l2.query_population(other,cid,ind.community_id,sid)
        b=snapshot(other,cid,ind.community_id,sid)
    assert a==b;engine.dispose()


def test_sterile_extinction_without_source_stays_extinct(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler,config=RenewalConfigL2(internal_dispersal_m=5));sid=ind.baseline['species_id']
    l2.disturb_population(db,cid,ind.community_id,sid,1037,'all-gone',experimental=True,sterilize_bank=True)
    advance_world_time(db,cid,10*YEAR);q=l2.query_population(db,cid,ind.community_id,sid)
    assert q['living_count']==0 and not q['children'] and q['ledger']['birth_events']==0
    old=service.materialize_individual(db,cid,point,sid,700)
    assert not old.state['alive']


def test_real_internal_route_without_collectable_propagule(db_session,sampler):
    db=db_session;cid=prepare(db,sampler);resources.initialize_resources(db,cid,experimental=True)
    eligible=[]
    for point,sid in candidates(42,'erva'):
        sp=sampler.catalog.species[sid];profile=l2.reproductive_profile(sp,100)
        if profile['blocked_reason']:continue
        if not any(p['parte'] in ('sementes','frutos','esporos','propagulos','ramos','fragmentos') for p in sp.parts()):eligible.append((point,sid))
    assert eligible
    point,sid=eligible[0];ind=service.materialize_individual(db,cid,point,sid,0)
    life.initialize_life(db,cid,experimental=True);l2.initialize_renewal(db,cid,experimental=True)
    cap=next(x['founder_count'] for x in sampler.sample(point)['populations'] if x['species_id']==sid)
    l2.disturb_population(db,cid,ind.community_id,sid,min(cap//2,300),'noncollectable',experimental=True)
    advance_world_time(db,cid,3*YEAR);q=l2.query_population(db,cid,ind.community_id,sid)
    events=[r for r in db.query(Event) if r.payload.get('renewal_signature')]
    assert q['children'] and events and all(e.payload['part_id'] is None for e in events)
    from app.db.models.item import ItemInstance
    assert db.query(ItemInstance).count()==0


@pytest.mark.parametrize('seed',[42,0,7,2026,12345])
def test_five_seeds_real_renewal_preserves_upstream(db_session,seed):
    v=inputs(seed);db=db_session;cid,point,ind,p=setup(db,v,seed);sid=ind.baseline['species_id']
    original=life.checksum(v.descriptor),life.checksum(v.water.to_dict())
    cap=next(x['founder_count'] for x in v.sample(point)['populations'] if x['species_id']==sid)
    l2.disturb_population(db,cid,ind.community_id,sid,cap*7//10,'five-seed',experimental=True)
    advance_world_time(db,cid,3*YEAR);q=l2.query_population(db,cid,ind.community_id,sid)
    assert q['living_count']<=cap and q['children'] and q['ledger']['birth_events']>0
    assert original==(life.checksum(v.descriptor),life.checksum(v.water.to_dict()))


def test_opt_in_corruption_and_transaction_rollback(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler);plan=l2.header(db,cid,sampler)
    with pytest.raises(ValueError):l2.initialize_renewal(db,cid,RenewalConfigL2(internal_dispersal_m=60),experimental=True)
    db.commit();before=deepcopy(plan.descriptor)
    l2.disturb_population(db,cid,ind.community_id,ind.baseline['species_id'],20,'rollback',experimental=True);db.rollback()
    q=l2.query_population(db,cid,ind.community_id,ind.baseline['species_id']);assert not q['children']
    assert q['living_count']==q['capacity'] and plan.descriptor==before
    plan.last_minute+=1;db.flush()
    with pytest.raises(ValueError,match='corrupted'):l2.header(db,cid,sampler)


def test_same_time_revisits_never_mint_packets_or_recruit(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler)
    l2.disturb_population(db,cid,ind.community_id,ind.baseline['species_id'],60,'revisit',experimental=True)
    advance_world_time(db,cid,YEAR);a=snapshot(db,cid,ind.community_id,ind.baseline['species_id'])
    for _ in range(3):assert snapshot(db,cid,ind.community_id,ind.baseline['species_id'])==a


def test_finite_bank_survives_parent_death_but_can_expire(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler,config=RenewalConfigL2(internal_dispersal_m=5));sid=ind.baseline['species_id']
    advance_world_time(db,cid,YEAR);before=l2.query_population(db,cid,ind.community_id,sid)
    assert before['bank_packets']>0
    l2.disturb_population(db,cid,ind.community_id,sid,1037,'dead-but-real-bank',experimental=True)
    q=l2.query_population(db,cid,ind.community_id,sid);assert q['bank_packets']==before['bank_packets'] and q['living_count']==0
    advance_world_time(db,cid,YEAR);q=l2.query_population(db,cid,ind.community_id,sid)
    events=[r for r in db.query(Event) if r.payload.get('renewal_signature')]
    assert all(e.payload['source_account']['produced_minute']<=YEAR for e in events)
    assert q['ledger']['expired_mg']>0
    for row in db.query(Population):l2._check(row)


def test_missing_route_and_exceptional_dependencies_stay_explicit():
    from app.game.world.genesis.vegetation.catalog import load_flora_catalog
    cat=load_flora_catalog()
    assert l2.reproductive_profile(cat.species['EV-FL-1139'],40)['blocked_reason']
    common=next(s for s in cat.species.values() if s.rarity_name=='comum' and not l2.reproductive_profile(s,100)['blocked_reason'])
    from dataclasses import replace
    a=l2.reproductive_profile(common,100);b=l2.reproductive_profile(replace(common,rarity_name='raro'),100)
    assert b['dispersal_m']<a['dispersal_m'] and b['establishment_chance_ppm']<a['establishment_chance_ppm']
    assert l2.reproductive_profile(replace(common,magic='excepcional'),100)['blocked_reason']=='exact_canonical_authorization_missing'


def test_migration_additive_and_campaign_reset(db_session,sampler):
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=Path(__file__).resolve().parents[2]/'alembic/versions/x32x5s6t7u8v_vegetation_renewal_l2.py'
    spec=importlib.util.spec_from_file_location('l2_migration',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.execute(sa.text('CREATE TABLE genesis_vegetation_life (campaign_id VARCHAR PRIMARY KEY)'))
        c.execute(sa.text("INSERT INTO genesis_vegetation_life VALUES ('old_L1')"))
        with Operations.context(MigrationContext.configure(c)):
            m.upgrade();assert c.execute(sa.text('SELECT count(*) FROM genesis_vegetation_renewal')).scalar()==0
            m.downgrade()
        assert c.execute(sa.text('SELECT campaign_id FROM genesis_vegetation_life')).scalar()=='old_L1'
    engine.dispose()
    db=db_session;cid,point,ind,p=setup(db,sampler)
    from app.game.world.reset import delete_campaign
    assert delete_campaign(db,cid);db.flush();assert db.get(Plan,cid) is None


def test_restart_reproduces_next_season_and_ids(db_session,sampler,tmp_path):
    import subprocess,sys,os
    db=db_session;cid,point,ind,p=setup(db,sampler);sid=ind.baseline['species_id']
    l2.disturb_population(db,cid,ind.community_id,sid,80,'restart',experimental=True);advance_world_time(db,cid,YEAR);l2.advance(db,cid,sampler);db.commit()
    path=tmp_path/'l2.sqlite';raw=db.get_bind().raw_connection()
    with sqlite3.connect(path) as target:raw.driver_connection.backup(target)
    raw.close();advance_world_time(db,cid,YEAR);expected=l2.query_population(db,cid,ind.community_id,sid)
    code='''import json,sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import models
from app.game.world.genesis.vegetation import renewal as l2
from app.game.world.genesis.vegetation.life_math import YEAR
from app.game.time.clock import advance_world_time
with Session(create_engine('sqlite:///'+sys.argv[1])) as db:
 advance_world_time(db,sys.argv[2],YEAR);q=l2.query_population(db,sys.argv[2],sys.argv[3],sys.argv[4]);db.commit();print('L2_RESULT:'+json.dumps(q,sort_keys=True))
'''
    result=subprocess.check_output([sys.executable,'-c',code,str(path),cid,ind.community_id,sid],env=dict(__import__('os').environ,PYTHONHASHSEED='383'),text=True)
    actual=json.loads(result.split('L2_RESULT:')[-1]);assert actual==expected


def test_existing_http_removal_replay_and_undo_include_l2(client,db_session,sampler):
    from app.tests.test_vegetation_lifecycle_l1 import setup as actor_setup
    db=db_session;cid,point,ind,p,actor,tool=actor_setup(db,sampler)
    l2.initialize_renewal(db,cid,experimental=True);db.commit()
    before=snapshot(db,cid,ind.community_id,ind.baseline['species_id']);db.commit()
    url=f'/api/campaigns/{cid}/actions';params={'character_id':actor.id}
    body={'text':'Derrubar a arvore','action_key':'L2-real-removal','plant_action':{'kind':'remove','individual_id':ind.individual_id,'tool_instance_id':tool.id}}
    r=client.post(url,params=params,json=body);assert r.status_code==200,r.text
    assert not r.json()['plant_result']['individual_alive']
    again=client.post(url,params=params,json=body);assert again.status_code==200,again.text
    undo=client.post(url+'/undo-last',params=params,json={'reason':'Desfazer remocao experimental'});assert undo.status_code==200,undo.text
    db.expire_all();assert snapshot(db,cid,ind.community_id,ind.baseline['species_id'])==before


def test_legacy_unmigrated_individuals_are_not_silently_converted(db_session,sampler):
    db=db_session;cid=prepare(db,sampler);point,sid=next(candidates(42,'arvore'))
    old=service.materialize_individual(db,cid,point,sid,0);original=deepcopy(old.baseline),deepcopy(old.state)
    resources.initialize_resources(db,cid,experimental=True);life.initialize_life(db,cid,experimental=True)
    with pytest.raises(ValueError,match='legacy non-R1'):l2.initialize_renewal(db,cid,experimental=True)
    assert l2.header(db,cid,sampler) is None and (old.baseline,old.state)==original


def test_late_registration_of_untouched_population_matches_early_visits(db_session,sampler):
    from app.game.world.genesis.geology.regional.experiment import window_point
    from app.game.world.genesis.sphere_topology import SurfacePoint
    db=db_session;cid,point,ind,p=setup(db,sampler)
    neighbor=service.materialize_community(db,cid,window_point(point,2000,0,sampler.radius))
    sid=next(x['species_id'] for x in neighbor.baseline['populations'] if not l2.reproductive_profile(sampler.catalog.species[x['species_id']],x['height_cm'])['blocked_reason'])
    db.commit();engine=clone_engine(db)
    early=l2.watch(db,cid,neighbor,sid,sampler)
    advance_world_time(db,cid,2*YEAR);l2.advance(db,cid,sampler);a=deepcopy(early.data)
    with Session(engine) as other:
        advance_world_time(other,cid,2*YEAR);l2.advance(other,cid,sampler)
        c=other.get(l2.Community,(cid,neighbor.community_id));late=l2.watch(other,cid,c,sid,sampler)
        assert late.data==a
    engine.dispose()


def test_slot_geometry_matches_L1_and_rejects_remote_face_projection(db_session,sampler):
    from app.game.world.genesis.sphere_topology import SurfacePoint,BASES
    db=db_session;cid,point,ind,p=setup(db,sampler)
    c=db.get(l2.Community,(cid,ind.community_id));pop=next(p for p in c.baseline['populations'] if p['species_id']==ind.baseline['species_id'])
    q=l2._slot_point(c,pop,ind.baseline['slot']);assert list(q.xyz)==ind.baseline['point']
    assert ind.baseline['slot'] in set(l2._near_slots(c,pop,q))
    assert list(l2._near_slots(c,pop,q))==list(l2._near_slots(c,pop,SurfacePoint(*(2*x for x in q.xyz))))
    normal,u,v=BASES[c.baseline['physical_address'][0]]
    assert not list(l2._near_slots(c,pop,SurfacePoint(*u)))
    assert not list(l2._near_slots(c,pop,SurfacePoint(*(-x for x in normal))))


def test_lazy_child_observation_materializes_physical_evidence_locally(db_session,sampler):
    from scripts.prove_vegetation import actor_at
    from app.db.models.world_environment import GenesisEnvironmentPoint
    db=db_session;cid,point,ind,p=setup(db,sampler);sid=ind.baseline['species_id']
    l2.disturb_population(db,cid,ind.community_id,sid,150,'lazy-child',experimental=True)
    advance_world_time(db,cid,YEAR);q=l2.query_population(db,cid,ind.community_id,sid);assert q['children']
    child=db.get(Individual,(cid,q['children'][0]['id']));count=db.query(GenesisEnvironmentPoint).count()
    actor,tool=actor_at(db,cid,child,sampler,tool_key='l2_observation_kit')
    observed=service.observe_individual(db,cid,actor.id,child.individual_id)
    assert observed['alive'] and observed['height_cm']==child.state['life']['height_cm'] and 'point' not in observed
    assert db.query(GenesisEnvironmentPoint).count()==count+1
