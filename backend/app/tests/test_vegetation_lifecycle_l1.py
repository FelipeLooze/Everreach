from copy import deepcopy
from dataclasses import replace
import json
import pytest
from app.game.world.genesis.vegetation import service,resources,lifecycle as life
from app.game.world.genesis.vegetation.life_math import *
from app.game.world.genesis.vegetation.catalog import load_flora_catalog
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.db.models.world_vegetation_lifecycle import GenesisVegetationLifeEvent as Event,GenesisLivingPopulation as Population
from app.db.models.world_vegetation import GenesisPlantIndividual as Individual
from app.game.time.clock import get_world_time,advance_world_time
from scripts.validate_plant_resources import inputs,actual_individual,prepare_operator,set_window,candidates
from scripts.prove_vegetation import prepare


@pytest.fixture(scope='module')
def sampler():return inputs(42)


def setup(db,v,kind='arvore',auto=False):
    cid=prepare(db,v);resources.initialize_resources(db,cid,experimental=True)
    point,ind,p=actual_individual(db,cid,v,42,kind)
    actor,tool=prepare_operator(db,cid,ind,v);set_window(db,cid,p,ind,v)
    life.initialize_life(db,cid,LifeConfigL1(automatic_colonization=auto),experimental=True)
    return cid,point,ind,p,actor,tool


def test_all_real_catalog_rarities_and_growth():
    counts={};cat=load_flora_catalog()
    for sp in cat.species.values():
        p=life_profile(sp);counts[p['rarity']]=counts.get(p['rarity'],0)+1
        lo,hi=RARITY[p['rarity']]
        assert all(lo<=d<=hi for d in p['recovery_days'].values())
        if sp.kind=='arvore':assert p['mature_active_days']>=600
    assert sum(counts.values())==3096
    assert life_profile(replace(cat.species['EV-FL-0001'],rarity=100))==life_profile(replace(cat.species['EV-FL-0001'],rarity=0))
    with pytest.raises(ValueError):LifeConfigL1(life_version=True)


@pytest.mark.parametrize('phase',[None,'flowering','fruiting'])
def test_calendar_integral_chunking_and_year_wrap(phase):
    rates=[Q,Q//3,0,Q//7];start=350*DAY;end=YEAR*16+100*DAY
    assert work(start,end,rates,phase=phase)==sum(work(a,b,rates,phase=phase) for a,b in zip([start,355*DAY,YEAR,7*YEAR],[355*DAY,YEAR,7*YEAR,end]))
    goal=work(start,end,rates,phase=phase)//2;t=time_for_work(start,goal,rates,phase=phase)
    assert work(start,t,rates,phase=phase)>=goal
    assert work(start,t-1,rates,phase=phase)<goal
    if phase:assert work(0,YEAR,[Q]*4,phase=phase)==180*DAY*Q


@pytest.mark.parametrize('days',[7,30,90,365])
def test_real_tree_gradual_recovery_and_time_semigroup(db_session,sampler,days):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler)
    before=deepcopy(ind.baseline);pid=p['id'];start=life.now(db,cid)
    r=service.harvest(db,cid,actor.id,ind.individual_id,pid,1,tool.id,'branch')
    assert r['individual_alive'] and ind.baseline==before
    snapshot=deepcopy(ind.state);end=start+days*DAY
    direct=life.project(ind.baseline,snapshot,end,sampler.catalog.species[ind.baseline['species_id']])
    split=snapshot
    for t in sorted(set([start+DAY,start+3*DAY,start+7*DAY,end])):
        if t<=end:split=life.project(ind.baseline,split,t,sampler.catalog.species[ind.baseline['species_id']])
    assert direct==split
    advance_world_time(db,cid,days*DAY);life.sync(db,cid,ind,sampler)
    assert ind.state==direct and ind.state['alive'] and ind.baseline==before
    assert ind.state['part_stock'][pid]>=snapshot['part_stock'][pid]
    replay=service.harvest(db,cid,actor.id,ind.individual_id,pid,1,tool.id,'branch')
    assert replay==r and ind.state==direct


def test_dead_tree_never_recovers_and_sparse_extinction(db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler)
    sid=ind.baseline['species_id'];service.remove_individual(db,cid,actor.id,ind.individual_id,tool.id,'fell')
    life.clear_population(db,cid,ind.community_id,sid,'local-extinction',reason='isolated explicit test disturbance',experimental=True)
    advance_world_time(db,cid,365*DAY);life.sync(db,cid,ind,sampler)
    assert not ind.state['alive'] and not any(ind.state['part_stock'].values())
    other=service.materialize_individual(db,cid,point,sid,1)
    assert not other.state['alive']
    c=service.query_community(db,cid,point);pop=next(x for x in c['populations'] if x['species_id']==sid)
    assert pop['living_count']==0 and pop['cover_ppm']==0 and db.query(Event).filter_by(status='pending').count()==0


def reproduction_setup(db,v,kind='erva'):
    cid,point,first,p,actor,tool=setup(db,v,kind)
    # Actual canonical seed-bearing population. Fixed physical neighbouring slots.
    from app.game.world.genesis.vegetation.actions import _nearby_slots
    c=db.get(life.Community,(cid,first.community_id));clock=get_world_time(db,cid)
    clock.month=7;clock.day=25 # actual summer fruiting window
    life.sync(db,cid,first,v)
    nearby=_nearby_slots(v,c,SurfacePoint(*first.baseline['point']),radius_m=40)
    for _,sid,slot,q in nearby:
        if sid!=first.baseline['species_id'] or slot==first.baseline['slot']:continue
        target=service.materialize_individual(db,cid,q,sid,slot)
        if not target.state['alive']:continue
        s=deepcopy(target.state);life.kill_state(s);life._store(target,s);life.record_death(db,cid,target,v)
        try:e=life.disperse(db,cid,first.individual_id,target.individual_id,'finite-test')
        except ValueError as exc:
            if str(exc).startswith('Propagation unavailable:'):continue
            raise
        return cid,first,target,e,point
    raise AssertionError('No actual finite nearby seed dispersal')


def test_real_seed_escrow_birth_growth_and_capacity(db_session,sampler):
    db=db_session;cid,parent,dead,e,point=reproduction_setup(db,sampler)
    state=deepcopy(parent.state);assert state['life']['dispersed_mass_mg']==e.payload['escrow_mass_mg']>0
    assert life.disperse(db,cid,parent.individual_id,dead.individual_id,'finite-test') is e and parent.state==state
    with pytest.raises(ValueError,match='vacant'):life.disperse(db,cid,parent.individual_id,dead.individual_id,'duplicate-slot')
    advance_world_time(db,cid,e.due_minute-life.now(db,cid));life.sync(db,cid,dead,sampler)
    child=db.get(Individual,(cid,e.payload['child_id']));assert child and child.individual_id!=dead.individual_id and child.state['life']['maturity']=='germinating'
    assert not any(child.state['part_stock'].values()) and not dead.state['alive']
    height=child.state['life']['height_cm'];advance_world_time(db,cid,30*DAY);life.sync(db,cid,child,sampler)
    assert child.state['life']['height_cm']>=height
    start=deepcopy(child.state);end=life.now(db,cid)+365*DAY;sp=sampler.catalog.species[child.baseline['species_id']]
    direct=life.project(child.baseline,start,end,sp);split=start
    for t in range(life.now(db,cid)+DAY,end+1,DAY):split=life.project(child.baseline,split,t,sp)
    assert direct==split
    c=service.query_community(db,cid,point);p=next(p for p in c['populations'] if p['species_id']==parent.baseline['species_id'])
    assert p['living_count']==p['founder_count']
    assert life.current_occupant(db,cid,dead,sampler).individual_id==child.individual_id


def test_young_tree_never_becomes_adult_in_week(db_session,sampler):
    db=db_session;cid,parent,dead,e,point=reproduction_setup(db,sampler,'arvore')
    advance_world_time(db,cid,e.due_minute-life.now(db,cid));life.sync(db,cid,dead,sampler)
    child=db.get(Individual,(cid,e.payload['child_id']))
    advance_world_time(db,cid,7*DAY);life.sync(db,cid,child,sampler)
    assert child.state['life']['maturity']!='adult' and child.state['life']['height_cm']<child.baseline['height_cm']
    assert not any(child.state['part_stock'].values())
    advance_world_time(db,cid,358*DAY);life.sync(db,cid,child,sampler)
    assert child.state['life']['maturity']!='adult' and not dead.state['alive']


@pytest.mark.parametrize('seed',[42,0,7,2026,12345])
def test_five_seed_real_recovery_unchanged_upstream(db_session,seed):
    v=inputs(seed);db=db_session;cid=prepare(db,v);resources.initialize_resources(db,cid,experimental=True)
    point,ind,p=actual_individual(db,cid,v,seed,'arvore');actor,tool=prepare_operator(db,cid,ind,v);set_window(db,cid,p,ind,v)
    upstream=(checksum(v.descriptor),checksum(v.water.to_dict()))
    life.initialize_life(db,cid,LifeConfigL1(automatic_colonization=False),experimental=True)
    service.harvest(db,cid,actor.id,ind.individual_id,p['id'],1,tool.id,'five-seed')
    assert ind.state['alive']
    for days in (7,23,60,275):advance_world_time(db,cid,days*DAY);life.sync(db,cid,ind,v);service._validate_individual(ind)
    assert upstream==(checksum(v.descriptor),checksum(v.water.to_dict()))


def test_lazy_implicit_founders_same_cutover_epoch(db_session,sampler):
    db=db_session;cid=prepare(db,sampler);resources.initialize_resources(db,cid,experimental=True)
    q,sid=next(candidates(42,'arvore'));life.initialize_life(db,cid,LifeConfigL1(automatic_colonization=False),experimental=True)
    early=service.materialize_individual(db,cid,q,sid,0);snapshot=deepcopy(early.state)
    advance_world_time(db,cid,365*DAY);late=service.materialize_individual(db,cid,q,sid,1)
    from app.game.world.genesis.vegetation.resources import initial_state
    initial=initial_state(late.baseline,{'alive':True,'part_stock':dict(late.baseline['initial_part_stock']),'revision':0})
    clone=Individual(campaign_id=cid,individual_id=late.individual_id,community_id=late.community_id,baseline=late.baseline,state=initial)
    life._attach(clone,life.header(db,cid,sampler),sampler)
    expected=life.project(clone.baseline,clone.state,life.now(db,cid),sampler.catalog.species[sid])
    assert late.state==expected


def test_invalid_action_rolls_back_ecological_projection(db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler);state=deepcopy(ind.state)
    advance_world_time(db,cid,30*DAY)
    with pytest.raises(ValueError):service.harvest(db,cid,actor.id,ind.individual_id,p['id'],999999,tool.id,'bad')
    assert ind.state==state


def test_l1_http_collection_undo_restores_life_and_time(client,db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler);db.commit();state=deepcopy(ind.state);minute=life.now(db,cid)
    url=f'/api/campaigns/{cid}/actions';params={'character_id':actor.id}
    body={'text':'Podar ramo','action_key':'l1-http','plant_action':{'kind':'harvest','individual_id':ind.individual_id,'part_id':p['id'],'quantity':1,'tool_instance_id':tool.id}}
    r=client.post(url,params=params,json=body);assert r.status_code==200,r.text
    assert r.json()['plant_result']['individual_alive']
    replay=client.post(url,params=params,json=body);assert replay.status_code==200,replay.text
    u=client.post(url+'/undo-last',params=params,json={'reason':'desfazer poda experimental'});assert u.status_code==200,u.text
    db.expire_all();assert db.get(Individual,(cid,ind.individual_id)).state==state and life.now(db,cid)==minute


def test_automatic_colonization_is_a_death_event_not_visit_roll(db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler,auto=True)
    service.remove_individual(db,cid,actor.id,ind.individual_id,tool.id,'death-with-neighbours')
    events=db.query(Event).filter_by(campaign_id=cid,status='pending').all()
    assert len(events)==1 and events[0].payload['parent_id']!=ind.individual_id
    descriptor=deepcopy(events[0].payload);parent=db.get(Individual,(cid,descriptor['parent_id']));state=deepcopy(parent.state)
    for _ in range(3):life.sync(db,cid,ind,sampler)
    assert db.query(Event).filter_by(campaign_id=cid,status='pending').count()==1 and parent.state==state
    assert not ind.state['alive']


def test_sqlite_restart_preserves_pending_birth_and_profile(db_session,sampler,tmp_path):
    import sqlite3,subprocess,sys,os
    db=db_session;cid,parent,dead,e,point=reproduction_setup(db,sampler)
    db.commit();path=tmp_path/'l1.sqlite';raw=db.get_bind().raw_connection()
    with sqlite3.connect(path) as target:raw.driver_connection.backup(target)
    raw.close()
    code='''import sys,json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import models
from app.db.models.world_vegetation import GenesisPlantIndividual as I
from app.db.models.world_vegetation_lifecycle import GenesisVegetationLifeEvent as E
from app.game.world.genesis.vegetation import lifecycle as l
from app.game.time.clock import advance_world_time
with Session(create_engine('sqlite:///'+sys.argv[1])) as db:
 e=db.get(E,(sys.argv[2],sys.argv[3]));advance_world_time(db,sys.argv[2],e.due_minute-l.now(db,sys.argv[2]));r=db.get(I,(sys.argv[2],e.payload['target_dead_id']));l.sync(db,sys.argv[2],r);db.commit();child=db.get(I,(sys.argv[2],e.payload['child_id']));print('L1_RESULT:'+json.dumps({'id':child.individual_id,'stage':child.state['life']['maturity'],'status':e.status}))
'''
    text= subprocess.check_output([sys.executable,'-c',code,str(path),cid,e.event_id],env=dict(os.environ,PYTHONHASHSEED='782'),text=True)
    result=json.loads(text.split('L1_RESULT:')[-1]);assert result=={'id':e.payload['child_id'],'stage':'germinating','status':'established'}


def test_l1_additive_migration_has_no_activation_or_legacy_rewrite():
    import importlib.util
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'alembic/versions/w31w4r5s6t7u_vegetation_life_l1.py'
    spec=importlib.util.spec_from_file_location('l1_migration',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=sa.create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.execute(sa.text('CREATE TABLE genesis_plant_resources (campaign_id VARCHAR PRIMARY KEY)'))
        c.execute(sa.text("INSERT INTO genesis_plant_resources VALUES ('legacy')"))
        with Operations.context(MigrationContext.configure(c)):
            m.upgrade();assert c.execute(sa.text('SELECT count(*) FROM genesis_vegetation_life')).scalar()==0
            m.downgrade()
        assert c.execute(sa.text('SELECT campaign_id FROM genesis_plant_resources')).scalar()=='legacy'
    engine.dispose()


def test_gradual_recovery_freezing_and_true_catalog_rare_delay(db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler)
    pid=p['id'];cap=ind.baseline['resource_profile']['parts'][pid]['max_units']
    n=0
    while ind.state['part_stock'][pid]:
        qty=min(ind.state['part_stock'][pid],ind.baseline['resource_profile']['parts'][pid]['per_action_max']);n+=1
        service.harvest(db,cid,actor.id,ind.individual_id,pid,qty,tool.id,f'finite-{n}')
    state=deepcopy(ind.state);start=life.now(db,cid);sp=sampler.catalog.species[ind.baseline['species_id']]
    after=life.project(ind.baseline,state,start+DAY,sp)
    assert 0<after['part_stock'][pid]<cap
    frozen=deepcopy(state);frozen['life']['rates']=[0]*4
    assert life.project(ind.baseline,frozen,start+365*DAY,sp)['part_stock'][pid]==0
    rare=replace(sp,rarity_name='raro');rare_state=deepcopy(state);rare_state['life']['profile']=life_profile(rare)
    rare_after=life.project(ind.baseline,rare_state,start+7*DAY,rare)
    assert rare_after['part_stock'][pid]<life.project(ind.baseline,state,start+7*DAY,sp)['part_stock'][pid]


def recolonization_setup(db,v):
    from app.game.world.genesis.vegetation.actions import _nearby_slots
    from app.game.world.genesis.terrain.address import point_on_face
    cid,point,original,p,actor,tool=setup(db,v)
    a,_=v.address(point);sid=original.baseline['species_id'];n=2**a.level
    # Real adjacent community, same species cohort, no synthetic habitat/population.
    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
        x,y=a.x+dx,a.y+dy
        if not 0<=x<n or not 0<=y<n:continue
        q=point_on_face(a.face,2*x+1,2*y+1,2*n)
        other=service.materialize_community(db,cid,q)
        if sid not in {p['species_id'] for p in other.baseline['populations']}:continue
        edge=point_on_face(a.face,2*a.x+1+dx,2*a.y+1+dy,2*n)
        target_c=db.get(life.Community,(cid,original.community_id))
        targets=[x for x in _nearby_slots(v,target_c,edge,radius_m=40) if x[1]==sid]
        parents=[x for x in _nearby_slots(v,other,edge,radius_m=40) if x[1]==sid]
        for _,_,ts,tq in targets:
            try:target=service.materialize_individual(db,cid,tq,sid,ts)
            except ValueError as exc:
                if 'microsite unsupported' in str(exc):continue
                raise
            for _,_,ps,pq in parents:
                try:parent=service.materialize_individual(db,cid,pq,sid,ps)
                except ValueError as exc:
                    if 'microsite unsupported' in str(exc):continue
                    raise
                if life.distance_m(v.environment.regional.terrain.plan.source.config,SurfacePoint(*target.baseline['point']),SurfacePoint(*parent.baseline['point']))>40:continue
                life.clear_population(db,cid,target.community_id,sid,'extinction',reason='isolated finite local disturbance',experimental=True)
                assert not target.state['alive'] and parent.state['alive']
                e=life.disperse(db,cid,parent.individual_id,target.individual_id,'external-recolonization')
                return cid,parent,target,e,tq
    raise AssertionError('No real neighbouring cohort found for recolonization')


def test_extinct_local_population_recolonizes_from_actual_neighbour(db_session,sampler):
    db=db_session;cid,parent,target,e,point=recolonization_setup(db,sampler)
    c=service.query_community(db,cid,point);pop=next(x for x in c['populations'] if x['species_id']==parent.baseline['species_id'])
    assert pop['living_count']==0
    advance_world_time(db,cid,e.due_minute-life.now(db,cid));life.sync(db,cid,target,sampler)
    c=service.query_community(db,cid,point);pop=next(x for x in c['populations'] if x['species_id']==parent.baseline['species_id'])
    assert pop['living_count']==1 and not target.state['alive'] and parent.state['alive']
    assert db.get(Individual,(cid,e.payload['child_id'])).baseline['parent_id']==parent.individual_id


def test_l1_is_opt_in_and_authority_corruption_never_regenerates(db_session,sampler):
    db=db_session;cid=prepare(db,sampler);resources.initialize_resources(db,cid,experimental=True)
    with pytest.raises(ValueError,match='experimental'):life.initialize_life(db,cid)
    assert life.header(db,cid,sampler) is None
    plan=life.initialize_life(db,cid,experimental=True)
    with pytest.raises(ValueError,match='reconfigure'):life.initialize_life(db,cid,LifeConfigL1(dispersal_m=50),experimental=True)
    d=deepcopy(plan.descriptor);d['rules']['calendar']='changed';plan.descriptor=d;db.flush()
    with pytest.raises(ValueError,match='corrupted'):life.header(db,cid,sampler)


def test_whole_root_collection_remains_fatal_in_l1(db_session,sampler):
    db=db_session;cid=prepare(db,sampler);resources.initialize_resources(db,cid,experimental=True)
    point,sid=next((q,sid) for q,sid in candidates(42,'erva') if any(p['parte']=='raiz' for p in sampler.catalog.species[sid].parts()))
    ind=service.materialize_individual(db,cid,point,sid,0)
    root=next(p for p in sampler.catalog.species[ind.baseline['species_id']].parts() if p['parte']=='raiz')
    actor,tool=prepare_operator(db,cid,ind,sampler);set_window(db,cid,root,ind,sampler)
    life.initialize_life(db,cid,LifeConfigL1(automatic_colonization=False),experimental=True)
    r=service.harvest(db,cid,actor.id,ind.individual_id,root['id'],1,tool.id,'whole-root')
    assert r['destructive'] and not r['individual_alive']
    advance_world_time(db,cid,365*DAY);life.sync(db,cid,ind,sampler)
    assert not ind.state['alive'] and not any(ind.state['part_stock'].values())


def test_stale_session_cannot_double_reserve_or_consume_propagule(db_session,sampler,tmp_path):
    import sqlite3
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    db=db_session;cid,parent,target,e,point=reproduction_setup(db,sampler);db.commit()
    path=tmp_path/'stale.sqlite';raw=db.get_bind().raw_connection()
    with sqlite3.connect(path) as c:raw.driver_connection.backup(c)
    raw.close();engine=create_engine('sqlite:///'+str(path))
    with Session(engine) as a,Session(engine) as b:
        pa=a.get(Individual,(cid,parent.individual_id));pb=b.get(Individual,(cid,parent.individual_id))
        state=deepcopy(pa.state)
        with pytest.raises(ValueError,match='vacant'):life.disperse(a,cid,pa.individual_id,target.individual_id,'conflict-A')
        a.rollback()
        with pytest.raises(ValueError,match='vacant'):life.disperse(b,cid,pb.individual_id,target.individual_id,'conflict-B')
        b.rollback();b.refresh(pb)
        assert pb.state==state and b.query(Event).filter_by(status='pending').count()==1
    engine.dispose()


def test_partial_collection_preserves_accumulated_growth(db_session,sampler):
    db=db_session;cid,point,ind,p,actor,tool=setup(db,sampler)
    service.harvest(db,cid,actor.id,ind.individual_id,p['id'],1,tool.id,'partial-first')
    advance_world_time(db,cid,180);life.sync(db,cid,ind,sampler)
    fraction=ind.state['life']['fraction'][p['id']];assert fraction>0
    s,mass=life.harvest_state(ind.baseline,ind.state,p['id'],1,life.now(db,cid))
    assert s['life']['fraction'][p['id']]==fraction and mass>0
