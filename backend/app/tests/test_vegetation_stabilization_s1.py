from copy import deepcopy
from dataclasses import replace
import json,sqlite3
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.game.world.genesis.vegetation import renewal as l2,lifecycle as life,sexual as sex,service
from app.game.world.genesis.vegetation.life_math import YEAR
from app.game.world.genesis.vegetation.recovery_structure import measure_community
from app.db.models.world_vegetation_sexual import GenesisVegetationSexualPolicy as Policy
from app.db.models.item import ItemInstance
from app.game.time.clock import advance_world_time
from scripts.validate_plant_resources import inputs
from app.tests.test_vegetation_renewal_l2 import setup,clone_engine,snapshot
from scripts.stabilize_vegetation import digest


@pytest.fixture(scope='module')
def sampler():return inputs(42)


def test_actual_audit_distinguishes_unspecified_vectors_from_obligations():
    from app.game.world.genesis.vegetation.catalog import load_flora_catalog
    cat=load_flora_catalog();assert sex.catalog_obligations()=={}
    flower=cat.species['EV-FL-1139'];assert sex.authorization(flower)==(True,None)
    special=json.loads(flower.growth_json);special['agente_polinizador_especifico_obrigatorio_id']='canonical_future_specialist'
    assert sex.authorization(replace(flower,growth_json=json.dumps(special)))[1]=='explicit_specialized_agent_or_condition_missing'
    assert not sex.authorization(replace(flower,magic='excepcional'))[0]
    assert not sex.specialized_requirements({'cultivo':{'aviso':'simbiota, polinizador ou salinidade podem impedir'}})
    assert sex.specialized_requirements({'reproducao':{'agente_especial_obrigatorio':True}})


@pytest.mark.parametrize('seed',[42,0,7,2026,12345])
def test_five_seed_common_flowers_reproduce_without_pollinator_entities(db_session,seed):
    v=inputs(seed);db=db_session;cid,point,ind,p=setup(db,v,seed,'flor');sid=ind.baseline['species_id']
    sig=l2.header(db,cid,v).signature;sex.initialize_sexual_policy(db,cid,experimental=True)
    assert l2.header(db,cid,v).signature==sig
    cap=next(x['founder_count'] for x in v.sample(point)['populations'] if x['species_id']==sid)
    l2.disturb_population(db,cid,ind.community_id,sid,min(150,cap//2),'sexual-flower',experimental=True)
    advance_world_time(db,cid,2*YEAR);q=l2.query_population(db,cid,ind.community_id,sid)
    assert q['children'] and q['living_count']<=cap
    events=[e for e in db.query(l2.Event) if e.payload.get('sexual_authorization')]
    assert events and db.query(ItemInstance).count()==0
    for e in events:
        a=e.payload['sexual_authorization'];assert a['mate_id']!=e.payload['parent_id'] and a['pollinator_entity'] is None
        assert e.payload['part_id'] is None


def test_single_mature_producer_does_not_assume_self_fertilization(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler,kind='flor');sid=ind.baseline['species_id']
    sex.initialize_sexual_policy(db,cid,experimental=True)
    c=db.get(l2.Community,(cid,ind.community_id));pop=next(x for x in c.baseline['populations'] if x['species_id']==sid)
    # An explicit controlled local disturbance leaves one mature producer.
    l2.disturb_population(db,cid,c.community_id,sid,pop['founder_count']-1,'one-mature',experimental=True,sterilize_bank=True)
    watched=db.get(l2.Renewing,(cid,pop['population_id']))
    seasons=life.life_profile(sampler.catalog.species[sid])['growth_seasons']
    first=next((m for m in l2.rounds(life.now(db,cid),life.now(db,cid)+YEAR) if life.work(m,m+1,watched.data['seasonal_rates'],seasons)>0),life.now(db,cid)+YEAR)
    advance_world_time(db,cid,first-life.now(db,cid));l2.advance(db,cid,sampler)
    row=db.get(l2.Renewing,(cid,pop['population_id']));assert row.data['ledger']['produced_packets']==0


def test_sexual_extension_preserves_the_exact_224_tree_recovery(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler);sid=ind.baseline['species_id']
    sex.initialize_sexual_policy(db,cid,experimental=True)
    l2.disturb_population(db,cid,ind.community_id,sid,700,'proof-logging',experimental=True)
    advance_world_time(db,cid,10*YEAR);q=l2.query_population(db,cid,ind.community_id,sid)
    assert q['living_count']==561 and len(q['children'])==224 and q['stages']['young']==78


def test_batch_and_reference_states_are_identical(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler);sid=ind.baseline['species_id']
    l2.disturb_population(db,cid,ind.community_id,sid,160,'batch-diff',experimental=True);db.commit();engine=clone_engine(db)
    advance_world_time(db,cid,3*YEAR);a=l2.query_population(db,cid,ind.community_id,sid);da=digest(db,cid)
    with Session(engine) as other:
        other.info[('L2_reference',cid)]=True;advance_world_time(other,cid,3*YEAR)
        b=l2.query_population(other,cid,ind.community_id,sid);assert a==b and digest(other,cid)==da
    engine.dispose()


def test_sexual_order_and_temporal_chunking(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler,kind='flor');sid=ind.baseline['species_id']
    sex.initialize_sexual_policy(db,cid,experimental=True)
    l2.disturb_population(db,cid,ind.community_id,sid,80,'sexual-chunk',experimental=True);db.commit();engine=clone_engine(db)
    advance_world_time(db,cid,2*YEAR);a=snapshot(db,cid,ind.community_id,sid)
    with Session(engine) as other:
        for _ in range(8):advance_world_time(other,cid,YEAR//4);l2.query_population(other,cid,ind.community_id,sid)
        b=snapshot(other,cid,ind.community_id,sid);assert a==b
    engine.dispose()


def test_crown_coverage_does_not_equate_count_with_forest_recovery(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler);sid=ind.baseline['species_id']
    original=measure_community(db,cid,ind.community_id,v=sampler,original=True)
    assert original['cover_ppm']==db.get(l2.Community,(cid,ind.community_id)).baseline['cover_ppm']
    l2.disturb_population(db,cid,ind.community_id,sid,700,'proof-logging',experimental=True)
    cut=measure_community(db,cid,ind.community_id,v=sampler);advance_world_time(db,cid,YEAR)
    q=l2.query_population(db,cid,ind.community_id,sid);after=measure_community(db,cid,ind.community_id,v=sampler)
    a=next(x for x in after['populations'] if x['species_id']==sid);o=next(x for x in original['populations'] if x['species_id']==sid)
    assert cut['tree_cover_ppm']<after['tree_cover_ppm']<original['tree_cover_ppm']
    assert a['cover_ppm']<o['cover_ppm']*a['living']//a['capacity']
    assert a['stages']['young']>0 and a['mean_height_cm']<o['mean_height_cm']
    assert sum(after['strata_cover_ppm'].values())==after['cover_ppm']
    assert after==measure_community(db,cid,ind.community_id,v=sampler)


def test_policy_is_explicit_prospective_and_corruption_fails(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler,kind='flor');sid=ind.baseline['species_id']
    with pytest.raises(ValueError):sex.initialize_sexual_policy(db,cid)
    initial_minute=life.now(db,cid)
    advance_world_time(db,cid,YEAR);l2.advance(db,cid,sampler)
    policy=sex.initialize_sexual_policy(db,cid,experimental=True)
    assert policy.descriptor['activation_minute']==initial_minute+YEAR
    row=db.query(l2.Renewing).filter_by(campaign_id=cid,species_id=sid).first()
    assert row.data['profile']['sexual_effective_minute']==initial_minute+YEAR and row.data['ledger']['produced_packets']==0
    policy.descriptor_checksum='corrupt';db.flush()
    with pytest.raises(ValueError,match='corrupted'):sex.header(db,cid)


def test_policy_rollback_and_no_duplicate_births(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler,kind='flor');db.commit()
    sex.initialize_sexual_policy(db,cid,experimental=True);db.rollback();assert db.get(Policy,cid) is None
    sex.initialize_sexual_policy(db,cid,experimental=True)
    l2.disturb_population(db,cid,ind.community_id,ind.baseline['species_id'],80,'no-dupes',experimental=True)
    advance_world_time(db,cid,YEAR);a=snapshot(db,cid,ind.community_id,ind.baseline['species_id'])
    assert snapshot(db,cid,ind.community_id,ind.baseline['species_id'])==a


def test_offseason_production_is_not_fabricated(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler,kind='flor');sid=ind.baseline['species_id']
    sex.initialize_sexual_policy(db,cid,experimental=True);advance_world_time(db,cid,YEAR//4);l2.advance(db,cid,sampler)
    row=db.query(l2.Renewing).filter_by(campaign_id=cid,species_id=sid).first()
    assert 'inverno' not in life.life_profile(sampler.catalog.species[sid])['growth_seasons']
    assert row.data['ledger']['produced_packets']==0


def test_sexual_policy_and_births_survive_restart(db_session,sampler,tmp_path):
    import subprocess,sys,os
    db=db_session;cid,point,ind,p=setup(db,sampler,kind='flor');sid=ind.baseline['species_id']
    sex.initialize_sexual_policy(db,cid,experimental=True);l2.disturb_population(db,cid,ind.community_id,sid,60,'s1-restart',experimental=True)
    advance_world_time(db,cid,YEAR);l2.query_population(db,cid,ind.community_id,sid);db.commit();path=tmp_path/'s1.sqlite';raw=db.get_bind().raw_connection()
    with sqlite3.connect(path) as target:raw.driver_connection.backup(target)
    raw.close();advance_world_time(db,cid,YEAR);expected=l2.query_population(db,cid,ind.community_id,sid)
    code='''import sys,json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import models
from app.game.world.genesis.vegetation import renewal as l2
from app.game.world.genesis.vegetation.life_math import YEAR
from app.game.time.clock import advance_world_time
with Session(create_engine('sqlite:///'+sys.argv[1])) as db:
 advance_world_time(db,sys.argv[2],YEAR);q=l2.query_population(db,sys.argv[2],sys.argv[3],sys.argv[4]);db.commit();print('S1_RESULT:'+json.dumps(q))
'''
    result=subprocess.check_output([sys.executable,'-c',code,str(path),cid,ind.community_id,sid],env=dict(os.environ,PYTHONHASHSEED='4239'),text=True)
    assert json.loads(result.split('S1_RESULT:')[-1])==expected


def test_sexual_policy_http_removal_replay_and_undo(client,db_session,sampler):
    from app.tests.test_vegetation_lifecycle_l1 import setup as actor_setup
    db=db_session;cid,point,ind,p,actor,tool=actor_setup(db,sampler,kind='flor')
    l2.initialize_renewal(db,cid,experimental=True);policy=sex.initialize_sexual_policy(db,cid,experimental=True);db.commit()
    before=snapshot(db,cid,ind.community_id,ind.baseline['species_id']);sig=policy.signature;db.commit()
    url=f'/api/campaigns/{cid}/actions';params={'character_id':actor.id}
    body={'text':'Remover planta','action_key':'S1-remove','plant_action':{'kind':'remove','individual_id':ind.individual_id,'tool_instance_id':tool.id}}
    a=client.post(url,params=params,json=body);assert a.status_code==200,a.text
    b=client.post(url,params=params,json=body);assert b.status_code==200,b.text
    undone=client.post(url+'/undo-last',params=params,json={'reason':'Desfazer remocao S1'});assert undone.status_code==200,undone.text
    db.expire_all();assert snapshot(db,cid,ind.community_id,ind.baseline['species_id'])==before and sex.header(db,cid).signature==sig


def test_additive_migration_has_no_activation_or_legacy_rewrite():
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=Path(__file__).resolve().parents[2]/'alembic/versions/y33y6t7u8v9w_vegetation_sexual_s1.py'
    spec=importlib.util.spec_from_file_location('s1_migration',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.execute(sa.text('CREATE TABLE genesis_vegetation_renewal (campaign_id VARCHAR PRIMARY KEY)'))
        c.execute(sa.text("INSERT INTO genesis_vegetation_renewal VALUES ('old_L2')"))
        with Operations.context(MigrationContext.configure(c)):
            m.upgrade();assert c.execute(sa.text('SELECT count(*) FROM genesis_vegetation_sexual_policy')).scalar()==0
            m.downgrade()
        assert c.execute(sa.text('SELECT campaign_id FROM genesis_vegetation_renewal')).scalar()=='old_L2'
    engine.dispose()


def test_site_position_cache_is_exact_bounded_and_radius_sensitive():
    from app.game.world.genesis.geology.regional.spatial import position_mm
    from app.game.world.genesis.sphere_topology import SurfacePoint,BASES
    position_mm.cache_clear()
    for normal,u,v in BASES:
        for radius in (6371000,63710000):
            q=SurfacePoint(*normal);a=position_mm(q,radius);assert a==position_mm.__wrapped__(q,radius)
            assert a==position_mm(q,radius)
    info=position_mm.cache_info();assert info.hits>=12 and info.maxsize==32768


def test_E1_read_memo_preserves_all_rules_and_typed_boolean_evidence(sampler):
    from app.game.world.genesis.vegetation.renewal_readview import ClassifierMemo
    from scripts.validate_plant_resources import candidates
    point,_=next(candidates(42,'arvore'));facts=sampler.environment.sample(point)['logical_facts']
    original=sampler.environment.classifier;memo=ClassifierMemo(original)
    for surface in (True,1,False,0,None,'true'):
        for temperature in (-5,0,12.5,35,None):
            f={**facts,'terreno.evidencia_superficie_continental':surface,'clima.temperatura_media_anual_c':temperature}
            assert memo.classify(f)==original.classify(f)
            assert memo.classify(f)==original.classify(f)
    assert memo.hits>0 and len(memo.cache)<=8192


def test_private_read_view_does_not_mutate_or_alias_E1(sampler):
    from app.game.world.genesis.vegetation.renewal_readview import read_view
    from scripts.validate_plant_resources import candidates
    view=read_view(sampler);point,_=next(candidates(42,'arvore'))
    expected=sampler.environment.sample(point);actual=view.environment.sample(point)
    assert actual==expected and view.environment is not sampler.environment
    with pytest.raises(TypeError):actual['results'][0]['state']='invalid_test_mutation'
    assert view.environment.sample(point)==expected and sampler.environment.sample(point)==expected


def test_read_memo_exact_topographic_boundaries(sampler):
    from app.game.world.genesis.vegetation.renewal_readview import ClassifierMemo
    from scripts.validate_plant_resources import candidates
    from fractions import Fraction
    q,_=next(candidates(42,'arvore'));facts=sampler.environment.sample(q)['logical_facts']
    original=sampler.environment.classifier;memo=ClassifierMemo(original)
    for value in (None,False,Fraction(-1,1000),0,Fraction(1,1000),100,1000,Fraction(1000001,1000),4000,9000):
        for slope in (0,30,90):
            f={**facts,'terreno.altitude_m':value,'terreno.declividade_graus':slope}
            assert memo.classify(f)==original.classify(f)


def test_S1_campaign_reset_removes_extension_before_L2(db_session,sampler):
    from app.game.world.reset import delete_campaign
    db=db_session;cid,point,ind,p=setup(db,sampler,kind='flor');sex.initialize_sexual_policy(db,cid,experimental=True)
    assert delete_campaign(db,cid);db.flush();assert db.get(Policy,cid) is None


def test_batch_failure_rolls_back_births_and_cleans_runtime(db_session,sampler):
    db=db_session;cid,point,ind,p=setup(db,sampler,kind='flor');sid=ind.baseline['species_id']
    sex.initialize_sexual_policy(db,cid,experimental=True);l2.disturb_population(db,cid,ind.community_id,sid,120,'bad-event',experimental=True)
    row=db.query(l2.Renewing).filter_by(campaign_id=cid,species_id=sid).first();seasons=life.life_profile(sampler.catalog.species[sid])['growth_seasons']
    at=next(m for m in l2.rounds(life.now(db,cid),life.now(db,cid)+YEAR) if life.work(m,m+1,row.data['seasonal_rates'],seasons)>0)
    advance_world_time(db,cid,at-life.now(db,cid));l2.advance(db,cid,sampler)
    pending=db.query(l2.Event).filter_by(campaign_id=cid,status='pending').first();assert pending
    old_checksum=pending.payload_checksum;pending.payload_checksum='corrupt';db.flush();frontier=l2.header(db,cid,sampler).last_minute
    advance_world_time(db,cid,YEAR)
    with pytest.raises(ValueError,match='corrupted'):l2.advance(db,cid,sampler)
    assert l2.header(db,cid,sampler).last_minute==frontier and ('L2_batch',cid) not in db.info and ('L2_advancing',cid) not in db.info
    pending=db.get(l2.Event,(cid,pending.event_id));pending.payload_checksum=old_checksum;db.flush()
    q=l2.query_population(db,cid,ind.community_id,sid);assert q['children']


def test_existing_L1_pending_dispersal_is_preserved_by_batch_executor(db_session,sampler):
    from app.tests.test_vegetation_lifecycle_l1 import reproduction_setup
    db=db_session;cid,parent,dead,event,point=reproduction_setup(db,sampler)
    assert not event.payload.get('renewal_signature')
    l2.initialize_renewal(db,cid,experimental=True);db.commit();engine=clone_engine(db)
    advance_world_time(db,cid,YEAR);a=l2.query_population(db,cid,dead.community_id,dead.baseline['species_id']);da=digest(db,cid)
    assert db.get(l2.Event,(cid,event.event_id)).status=='established'
    with Session(engine) as other:
        other.info[('L2_reference',cid)]=True;advance_world_time(other,cid,YEAR)
        b=l2.query_population(other,cid,dead.community_id,dead.baseline['species_id'])
        assert a==b and digest(other,cid)==da
    engine.dispose()
