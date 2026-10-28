from copy import deepcopy
from dataclasses import replace
import json

import pytest
from sqlalchemy.orm import Session

from app.game.time.clock import advance_world_time
from app.game.world.genesis.vegetation import lifecycle as life, renewal as l2
from app.game.world.genesis.vegetation.catalog import load_flora_catalog
from app.game.world.genesis.vegetation.growth_gameplay import (
    LifeConfigGA1, attach_profile, pacing_class, parse_config,
)
from app.game.world.genesis.vegetation.life_math import (
    DAY, Q, LifeConfigL1, life_profile, maturity_minute,
)
from app.tests.test_vegetation_renewal_l2 import clone_engine, snapshot
from scripts.review_genesis_gameplay import run, setup
from scripts.validate_plant_resources import inputs


@pytest.fixture(scope='module')
def sampler():
    return inputs(42)


def test_old_schema_profile_and_dispatch_are_exactly_preserved():
    cfg = LifeConfigL1()
    assert 'growth_policy' not in cfg.model_dump()
    assert type(parse_config(cfg.model_dump(mode='json'))) is LifeConfigL1
    for sp in load_flora_catalog().species.values():
        profile, rates = attach_profile(sp, cfg, {'individual_id':'proof'}, [0,Q,0,Q])
        assert profile == life_profile(sp, cfg) and rates is None


def test_all_real_species_pacing_is_deterministic_and_exceptionals_stay_legacy():
    cfg = LifeConfigGA1()
    for sp in load_flora_catalog().species.values():
        p, rates = attach_profile(sp, cfg, {'individual_id':sp.id}, [0,Q,0,Q])
        if sp.magic == 'excepcional':
            assert p == life_profile(sp) and rates is None
        else:
            lo,hi = cfg.bands_days[p['pacing_class']]
            assert lo <= p['mature_active_days'] <= hi
            assert min(rates) >= 807500 and max(rates) <= 1102500
            assert (p,rates) == attach_profile(sp,cfg,{'individual_id':sp.id},[0,Q,0,Q])
            # Neither growth duration nor pace reads the ecological rarity score/name.
            other = replace(sp, rarity=100-sp.rarity, rarity_name='muito_raro')
            p2,r2=attach_profile(other,cfg,{'individual_id':sp.id},[0,Q,0,Q])
            assert p2['mature_active_days']==p['mature_active_days'] and r2==rates


def test_calendar_lower_bound_and_reviewed_tree_classes():
    sp=next(s for s in load_flora_catalog().species.values() if s.kind=='arvore' and s.magic!='excepcional')
    for label in ('tree','large_tree','slow_tree','legacy'):
        cfg=LifeConfigGA1(tree_pacing={sp.id:label})
        assert pacing_class(sp,cfg)==label
        profile,rates=attach_profile(sp,cfg,{'individual_id':'real'},[0]*4)
        if label=='legacy':assert rates is None;continue
        state={'birth_minute':10*DAY,'profile':profile,'rates':[0]*4,'growth_rates_ppm':rates}
        elapsed=(maturity_minute(state)-state['birth_minute'])/DAY
        assert cfg.bands_days[label][0]/1.1025 <= elapsed <= cfg.bands_days[label][1]/0.8075+1/DAY
    with pytest.raises(ValueError):LifeConfigGA1(bands_days={'tree':[1,2]})
    with pytest.raises(ValueError):parse_config({'growth_policy':'unknown'})
    with pytest.raises(ValueError):LifeConfigGA1(minimum_rate_ppm=0)


@pytest.mark.parametrize('kind',['flor','erva','arbusto','arvore'])
def test_real_persistent_births_grow_in_calendar_days(tmp_path,kind):
    r=run(42,kind,'GA1',tmp_path)
    assert r['birth_event_id'] and r['child_id'].startswith('vgi:l2:')
    assert [s['days_since_birth'] for s in r['snapshots']]==[7,15,30,60]
    assert r['snapshots'][0]['height_cm']>1
    assert r['snapshots'][-1]['maturity']=='adult'
    assert all(s['population_living']<=r['capacity'] for s in r['snapshots'])
    assert (tmp_path/f'GA1-{kind}-42.sqlite').exists()


def test_g1_signature_reconfiguration_and_corruption_are_explicit(db_session,sampler):
    db=db_session;cid,point,parent,_=setup(db,sampler,'arvore',42,LifeConfigGA1())
    p=life.header(db,cid,sampler)
    assert p.descriptor['kind']=='vegetation_life_l1_ga1'
    assert type(parse_config(p.descriptor['config'])) is LifeConfigGA1
    with pytest.raises(ValueError,match='reconfigure'):
        life.initialize_life(db,cid,LifeConfigL1(),experimental=True)
    with pytest.raises(ValueError,match='Explicit'):
        life.initialize_life(db,cid,LifeConfigGA1())
    p.descriptor_checksum='corrupt';db.flush()
    with pytest.raises(ValueError,match='corrupted'):life.header(db,cid,sampler)


def test_existing_l1_cannot_be_silently_switched_to_g1(db_session,sampler):
    db=db_session;cid,_,_,_=setup(db,sampler,'arvore',42,LifeConfigL1())
    before=deepcopy(life.header(db,cid,sampler).descriptor)
    with pytest.raises(ValueError,match='reconfigure'):
        life.initialize_life(db,cid,LifeConfigGA1(),experimental=True)
    assert life.header(db,cid,sampler).descriptor==before


def test_g1_batch_reference_restart_revisits_and_temporal_chunking(db_session,sampler):
    db=db_session;cid,_,parent,_=setup(db,sampler,'arvore',42,LifeConfigGA1())
    sid=parent.baseline['species_id'];l2.disturb_population(db,cid,parent.community_id,sid,80,'ga1-timing',experimental=True)
    db.commit();engine=clone_engine(db)
    advance_world_time(db,cid,360*DAY);a=snapshot(db,cid,parent.community_id,sid)
    # Independent ORM session, original executor, fragmented visits and same final minute.
    with Session(engine) as other:
        other.info[('L2_reference',cid)]=True
        for days in (7,8,15,30,60,120,120):
            advance_world_time(other,cid,days*DAY);l2.query_population(other,cid,parent.community_id,sid)
        b=snapshot(other,cid,parent.community_id,sid)
        assert a==b
        assert snapshot(other,cid,parent.community_id,sid)==b
    engine.dispose()


def test_g1_failed_transaction_does_not_erase_removal_or_recreate_founders(db_session,sampler):
    db=db_session;cid,_,parent,_=setup(db,sampler,'arvore',42,LifeConfigGA1())
    sid=parent.baseline['species_id'];l2.disturb_population(db,cid,parent.community_id,sid,50,'ga1-cut',experimental=True)
    db.commit();before=snapshot(db,cid,parent.community_id,sid);db.commit()
    advance_world_time(db,cid,90*DAY);l2.query_population(db,cid,parent.community_id,sid)
    db.rollback();db.expire_all()
    assert snapshot(db,cid,parent.community_id,sid)==before


def test_g1_projection_semigroup_mass_and_dead_state(db_session,sampler):
    db=db_session;cid,_,parent,_=setup(db,sampler,'arvore',42,LifeConfigGA1())
    sp=sampler.catalog.species[parent.baseline['species_id']]
    # Exercise the pure contract on the real adult baseline without granting a birth or stock.
    initial=deepcopy(parent.state);l=initial['life'];start=life.now(db,cid)
    l.update(birth_minute=start,last_minute=start,mature_tissues_initialized=False,maturity='germinating')
    initial['part_stock']={k:0 for k in initial['part_stock']}
    direct=life.project(parent.baseline,initial,start+60*DAY,sp);split=initial
    for days in (7,15,30,60):split=life.project(parent.baseline,split,start+days*DAY,sp)
    assert split==direct;life.validate(parent.baseline,direct)
    dead=deepcopy(parent.state);life.kill_state(dead)
    future=life.project(parent.baseline,dead,start+60*DAY,sp)
    assert not future['alive'] and not any(future['part_stock'].values())


def test_ga1_http_collection_replay_undo_preserves_new_growth_state(client,db_session,sampler):
    from scripts.validate_plant_resources import prepare_operator,set_window
    from app.game.world.genesis.vegetation import service
    db=db_session;cid,_,parent,part=setup(db,sampler,'arvore',42,LifeConfigGA1())
    actor,tool=prepare_operator(db,cid,parent,sampler);set_window(db,cid,part,parent,sampler)
    life.sync(db,cid,parent,sampler);before=deepcopy(parent.state);minute=life.now(db,cid);db.commit()
    assert before['life']['profile']['growth_policy']=='adventure_calendar_ga1'
    url=f'/api/campaigns/{cid}/actions';params={'character_id':actor.id}
    body={'text':'Podar ramo','action_key':'ga1-undo','plant_action':{
        'kind':'harvest','individual_id':parent.individual_id,'part_id':part['id'],
        'quantity':1,'tool_instance_id':tool.id}}
    result=client.post(url,params=params,json=body);assert result.status_code==200,result.text
    repeat=client.post(url,params=params,json=body);assert repeat.json()==result.json()
    undo=client.post(url+'/undo-last',params=params,json={'reason':'desfazer coleta GA1'})
    assert undo.status_code==200,undo.text
    db.expire_all();assert db.get(life.Individual,(cid,parent.individual_id)).state==before
    assert life.now(db,cid)==minute


def test_ga1_invalid_tree_assignment_is_rejected_before_activation(db_session,sampler):
    from scripts.prove_vegetation import prepare
    from app.game.world.genesis.vegetation import resources
    db=db_session;cid=prepare(db,sampler);resources.initialize_resources(db,cid,experimental=True)
    flower=next(s for s in sampler.catalog.species.values() if s.kind=='flor')
    with pytest.raises(ValueError,match='real tree'):
        life.initialize_life(db,cid,LifeConfigGA1(tree_pacing={flower.id:'slow_tree'}),experimental=True)
    assert life.header(db,cid,sampler) is None
