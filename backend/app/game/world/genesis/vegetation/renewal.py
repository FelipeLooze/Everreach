"""L2 recurring finite population renewal. Opt-in extension; L1 stays reproducible.

Only disturbed/explicitly registered populations run quarterly ecological events.
Implicit mature founders remain cohorts, never millions of database individuals.
Internal propagules are not canonical inventory parts or claims of measured water.
"""
from copy import deepcopy
from math import gcd
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.db.models.world_vegetation_renewal import GenesisVegetationRenewal as Plan,GenesisRenewingPopulation as Renewing
from app.db.models.world_vegetation_lifecycle import GenesisLivingPopulation as Population,GenesisVegetationLifeEvent as Event
from app.db.models.world_vegetation import GenesisVegetationCommunity as Community,GenesisPlantIndividual as Individual
from ..terrain.field import checksum
from ..terrain.address import point_on_face,chart
from ..sphere_topology import SurfacePoint
from ..sphere_metric import distance_m
from .life_math import DAY,YEAR,Q,work,life_profile
from . import lifecycle as life,resources,service

STEP=90*DAY;OFFSET=30*DAY
CHANCES={'arvore':30000,'arbusto':70000,'erva':140000,'flor':160000,'graminea':120000,
    'musgo':50000,'liquen':12000,'samambaia':80000,'trepadeira':60000,'fungo':100000,'junco':90000,'alga':100000,'consorcio_simbiotico':10000}


class RenewalConfigL2(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid',strict=True)
    renewal_version: Literal[2]=2
    annual_reserve_ppm: int=Field(default=1000,ge=100,le=5000)
    bank_packets_per_adult: int=Field(default=4,ge=1,le=8)
    internal_dispersal_m: int=Field(default=40,ge=5,le=200)

    @field_validator('renewal_version',mode='before')
    @classmethod
    def strict_version(cls,v):
        if type(v)is not int:raise ValueError('Explicit L2 version required')
        return v


def rules():
    return {'version':2,'event_step_minutes':STEP,'offset':OFFSET,'chances_ppm':CHANCES,
        'cohort':'finite_established_founders_and_mature_children_v1','reserve':'new_assimilation_separate_from_R1_harvest_pools',
        'mechanisms':'declared_abiotic_spores_or_vegetative_routes_only_v1','full_clear_probes':64,
        'viability_days':{'abiotic_spore_internal':360,'vegetative_internal':180},
        'tombstone_time_policy':'immutable_founder_death_separate_from_latest_vacancy',
        'identity':'signature_population_slot_generation_round_v1','calendar':'authoritative_360_day_year'}


def header(db,cid,v):
    p=db.get(Plan,cid,populate_existing=True)
    if p is None:return None
    d=p.descriptor;l=life.header(db,cid,v)
    cfg=parse_config(d['config'])
    expected=policy_rules(cfg)
    if (checksum(d)!=p.descriptor_checksum or checksum(d)[:24]!=p.signature or d.get('rules')!=expected or
        d.get('version')!=2 or l is None or d['L1_signature']!=l.signature or
        p.state_checksum!=checksum([p.signature,p.last_minute])):raise ValueError('L2 authority/frontier corrupted or changed')
    return p


def parse_config(data):
    if 'renewal_policy' in data:
        from .renewal_gameplay import RenewalConfigGA2
        return RenewalConfigGA2.model_validate(data)
    return RenewalConfigL2.model_validate(data)


def policy_rules(config):
    if hasattr(config,'renewal_policy'):
        from .renewal_gameplay import rules as ga2_rules
        return ga2_rules()
    return rules()


def initialize_renewal(db,cid,config=None,*,experimental=False):
    if experimental is not True:raise ValueError('Explicit experimental L2 activation required')
    v=service.context(db,cid);l=life.header(db,cid,v)
    if l is None:raise ValueError('Explicit L1 required before L2')
    cfg=parse_config((config or RenewalConfigL2()).model_dump(mode='json'));old=header(db,cid,v)
    if hasattr(cfg,'renewal_policy'):
        from .growth_gameplay import LifeConfigGA1
        if not isinstance(life.parse_config(l.descriptor['config']),LifeConfigGA1):raise ValueError('GA2 requires GA1')
    if old:
        if old.descriptor['config']!=cfg.model_dump(mode='json'):raise ValueError('Cannot reconfigure L2')
        return old
    service._fence(db,cid)
    # Cut over existing L1 events/states at the real present, never replay old history.
    established=list(db.query(Individual).filter_by(campaign_id=cid))
    if any('resource_signature' not in row.baseline for row in established):
        raise ValueError('L2 requires explicit reconciliation of legacy non-R1 individuals')
    for row in established:
        life.sync(db,cid,row,v)
    minute=life.now(db,cid)
    d={'kind':'vegetation_renewal_l2','version':2,'L1_signature':l.signature,'activation_minute':minute,
        'config':cfg.model_dump(mode='json'),'rules':policy_rules(cfg),'legacy_policy':'explicit_activation_no_rewrite'}
    if hasattr(cfg,'renewal_policy'):d['kind']='vegetation_renewal_ga2'
    sig=checksum(d)[:24];p=Plan(campaign_id=cid,signature=sig,descriptor=d,descriptor_checksum=checksum(d),last_minute=minute,state_checksum=checksum([sig,minute]))
    db.add(p);db.flush()
    for c in db.query(Community).filter_by(campaign_id=cid).order_by(Community.community_id):
        for pop in c.baseline['populations']:
            # GA2 watches actual participants and disturbance/border sources.
            # Unaffected full communities retain implicit deterministic history.
            if hasattr(cfg,'renewal_policy') and not any(x.community_id==c.community_id and x.baseline['species_id']==pop['species_id'] for x in established):continue
            watch(db,cid,c,pop['species_id'],v,p)
    return p


def reproductive_profile(sp,height_cm,config=None):
    cfg=config or RenewalConfigL2();traits=json.loads(sp.growth_json or '{}');strategy=traits.get('estrategia_reprodutiva_proposta','unknown')
    # No inferred pollination vector. A declared vegetative alternative avoids that dependency.
    if sp.magic=='excepcional':mechanism=None;reason='exact_canonical_authorization_missing'
    elif any(x in strategy for x in ('fragment','divisao','estacas','rizomas','rebrotamento')):mechanism='vegetative_internal';reason=None
    elif 'esporos' in strategy:mechanism='abiotic_spore_internal';reason=None
    else:mechanism=None;reason='pollination_or_vector_or_propagule_mechanism_unconfirmed'
    body=resources.derive(sp,height_cm)['standing_biomass_mg']
    mass=max(1,body//(1000000 if mechanism=='abiotic_spore_internal' else 10000))
    annual=max(4,body*cfg.annual_reserve_ppm//Q);units=min(2,annual//(4*mass))
    rarity=life_profile(sp)['rarity'];factor={'comum':1000,'incomum':800,'raro':600,'muito_raro':400,'excepcional':0}[rarity]
    return {'version':2,'species_id':sp.id,'canonical_strategy':strategy,'mechanism':mechanism,'blocked_reason':reason,
        'unit_mass_mg':mass,'annual_modeled_reserve_per_adult_mg':annual,'packets_per_adult_per_period':units,
        'viability_minutes':rules()['viability_days']['abiotic_spore_internal' if mechanism=='abiotic_spore_internal' else 'vegetative_internal']*DAY,
        'dispersal_m':max(1,cfg.internal_dispersal_m*factor//1000),
        'establishment_chance_ppm':CHANCES[sp.kind]*factor//1000,
        'source':'v22_declared_strategy_plus_versioned_gameplay_estimates_not_measured_fertility',
        'inventory_item_id':None,'canonical_collectable_part_id':None}


def _put(row,d):
    from sqlalchemy.orm import object_session
    session=object_session(row);runtime=session.info.get(('L2_batch',row.campaign_id)) if session else None
    if runtime is not None:return runtime.stage(row,d)
    validate(d);row.data=d;row.data_checksum=checksum(d)


def validate(d):
    s=d['ledger'];quantities=[s[k] for k in ('produced_mg','dispersed_mg','expired_mg','failed_mg')]
    if any(type(x)is not int or x<0 for x in quantities):raise ValueError('Invalid L2 finite reserve')
    bank=sum(b['remaining']*b['unit_mass_mg'] for b in d['bank'])
    if s['produced_mg']!=bank+s['dispersed_mg']+s['expired_mg']+s['failed_mg']:raise ValueError('L2 reserve conservation mismatch')
    for b in d['bank']:
        if not 0<=b['remaining']<=b['produced'] or any(n>b['per_parent'] for n in b['used'].values()):raise ValueError('L2 propagule capacity exceeded')
    if d['profile'].get('renewal_policy')=='adventure_renewal_ga2' and 'ga2_budget' in d:
        b=d['ga2_budget'];rate=d['profile']['annual_packets_per_mature_adult']
        if (any(type(n)is not int or n<0 for n in b.values()) or b['remainder']>=YEAR*Q or
            b['earned_tokens']!=b['producer_work_ppm_minutes']*rate//(YEAR*Q) or
            b['earned_tokens']!=s['produced_packets']+b['discarded_tokens']):
            raise ValueError('GA2 time-rated reproductive budget violated')


def _check(row):
    from sqlalchemy.orm import object_session
    session=object_session(row);runtime=session.info.get(('L2_batch',row.campaign_id)) if session else None
    if runtime is not None and runtime.staged(row):return
    if checksum(row.data)!=row.data_checksum:raise ValueError('L2 population corrupted')
    validate(row.data)
    if row.data['profile'].get('sexual_policy_signature'):
        from .sexual import validate_profile
        validate_profile(session,row.campaign_id,row.data['profile'])


def watch(db,cid,c,sid,v,p=None):
    p=p or header(db,cid,v)
    if p is None:return None
    source=next(x for x in c.baseline['populations'] if x['species_id']==sid)
    db.flush();old=db.get(Renewing,(cid,source['population_id']),populate_existing=True)
    if old:_check(old);return old
    cfg=parse_config(p.descriptor['config'])
    registration=('GA2_registering',cid,source['population_id'])
    if hasattr(cfg,'renewal_policy') and not db.info.get(registration):
        # Registration and implicit full-history reconstruction must succeed
        # together. A failed late registration must remain retryable, not leave
        # an empty authority that skips its historical budgets on the next visit.
        service._fence(db,cid)
        with db.begin_nested():
            db.info[registration]=True
            try:return watch(db,cid,c,sid,v,p)
            finally:db.info.pop(registration,None)
    native=life.population(db,cid,c,sid)
    from .sexual import header as sexual_header,extend_profile
    profile=extend_profile(reproductive_profile(v.catalog.species[sid],source['height_cm'],cfg),v.catalog.species[sid],sexual_header(db,cid,p.signature))
    if hasattr(cfg,'renewal_policy'):
        from .renewal_gameplay import configure_profile
        profile=configure_profile(profile,v.catalog.species[sid],life.parse_config(life.header(db,cid,v).descriptor['config']),cfg)
    d={'version':2,'signature':p.signature,'capacity':source['founder_count'],
        'profile':profile,
        'vacancies':{s:life.now(db,cid) for s,e in native.data['slots'].items() if not e.get('occupant') and not e.get('reservation')},
        'all_dead_at':native.data.get('cleared_minute'),'bank':[],
        'founder_deaths':{},'founders_cleared_at':native.data.get('cleared_minute'),
        'seasonal_rates':life.rates(v,{'point':c.baseline['point']},v.catalog.species[sid]),
        'ledger':{'produced_mg':0,'dispersed_mg':0,'expired_mg':0,'failed_mg':0,'produced_packets':0,'attempts':0,'birth_events':0},
        'registered_minute':p.descriptor['activation_minute']}
    row=Renewing(campaign_id=cid,population_id=source['population_id'],community_id=c.community_id,species_id=sid,data=d,data_checksum=checksum(d))
    db.add(row);db.flush()
    # A never-disturbed implicit population was full before registration. Reconstruct
    # its cohort-level history, including expired reserves, independently of visits.
    activation=p.descriptor['activation_minute'];end=p.last_minute
    if not d['vacancies'] and d['all_dead_at'] is None:
        if hasattr(cfg,'renewal_policy'):
            from .renewal_gameplay import catch_up_full
            catch_up_full(db,cid,row,v,p,activation,end)
        else:
            for minute in rounds(activation,end):_produce(db,cid,row,v,p,minute)
    return row


def rounds(start,end):
    k=max(0,(start-OFFSET)//STEP+1)
    while OFFSET+k*STEP<=end:
        yield OFFSET+k*STEP;k+=1


def _native(db,cid,popid):
    runtime=db.info.get(('L2_batch',cid))
    if runtime is not None:return runtime.native(popid)
    r=db.get(Population,(cid,popid),populate_existing=True)
    if r is None or checksum(r.data)!=r.data_checksum:raise ValueError('Missing/corrupt L2 physical occupancy')
    return r


def _entity(db,cid,model,identifier,v=None):
    # Strong references prevent SQLAlchemy's weak identity map from reloading the
    # same immutable community / participating child for every seasonal event.
    cache=db.info.get(('L2_entities',cid))
    key=(model.__name__,identifier)
    if cache is not None and key in cache:return cache[key]
    row=db.get(model,(cid,identifier),populate_existing=True)
    if row is None:raise ValueError('Missing L2 participating entity')
    if model is Community:service._validate_community(row,v)
    else:service._validate_individual(row)
    if cache is not None:cache[key]=row
    return row


def _produce(db,cid,row,v,p,minute):
    _check(row);d=deepcopy(row.data);profile=d['profile']
    # Expiration is analytical at ecological boundaries; unavailable packets cannot be spent.
    kept=[]
    for b in d['bank']:
        if b['expires']<=minute:d['ledger']['expired_mg']+=b['remaining']*b['unit_mass_mg']
        else:kept.append(b)
    d['bank']=kept
    if profile['blocked_reason'] or not profile['packets_per_adult_per_period']:_put(row,d);return
    c=_entity(db,cid,Community,row.community_id,v);source=next(x for x in c.baseline['populations'] if x['species_id']==row.species_id)
    sp=v.catalog.species[row.species_id];b={'point':c.baseline['point']}
    if 'seasonal_rates' not in d:d['seasonal_rates']=life.rates(v,b,sp)
    activity=d['seasonal_rates'];seasons=life_profile(sp)['growth_seasons']
    if work(minute,minute+1,activity,seasons)==0:_put(row,d);return
    native=_native(db,cid,row.population_id);slots=native.data['slots'];children=[]
    for slot,e in slots.items():
        if not e.get('occupant'):continue
        child=_entity(db,cid,Individual,e['occupant'])
        if child.state['life']['last_minute']>minute:raise ValueError('L2 historical frontier violation')
        runtime=db.info.get(('L2_batch',cid))
        if runtime is not None:is_adult=runtime.adult(child,minute)
        else:
            s=life.project(child.baseline,child.state,minute,sp);is_adult=s['alive'] and s['life']['maturity']=='adult'
        if is_adult:children.append({'slot':int(slot),'id':child.individual_id,'point':child.baseline['point']})
    cleared=native.data.get('cleared_minute') is not None
    adults=(0 if cleared else source['founder_count']-len(slots))+len(children)
    if profile.get('sexual_policy_revision'):
        if minute<profile['sexual_effective_minute'] or adults<profile['minimum_mature_producers']:_put(row,d);return
    cfg=RenewalConfigL2.model_validate(p.descriptor['config']);room=max(0,adults*cfg.bank_packets_per_adult-sum(b['remaining'] for b in d['bank']))
    amount=min(room,adults*profile['packets_per_adult_per_period'])
    if amount:
        bid='l2bank:'+checksum([p.signature,row.population_id,minute])[:32]
        cohort={'founder_capacity':source['founder_count'],'all_founders_dead':cleared,'excluded_founders':sorted(map(int,slots)),
            'mature_children':children,'adults':adults}
        d['bank'].append({'id':bid,'created':minute,'expires':minute+profile['viability_minutes'],'produced':amount,'remaining':amount,
            'unit_mass_mg':profile['unit_mass_mg'],'per_parent':profile['packets_per_adult_per_period'],'used':{},'cohort':cohort,
            'origin_population_id':row.population_id,'reserve_is_modeled':True})
        d['ledger']['produced_mg']+=amount*profile['unit_mass_mg'];d['ledger']['produced_packets']+=amount
    _put(row,d);db.flush()


def _slot_point(c,pop,slot):
    face,level,x,y=c.baseline['physical_address'];grid=1
    while grid*grid<pop['founder_count']:grid*=2
    salt=int(checksum([pop['population_id'],'position'])[:16],16)
    index=(slot*(2*(salt//(grid*grid))+1)+salt)%(grid*grid)
    return point_on_face(face,2*x*grid+2*(index%grid)+1,2*y*grid+2*(index//grid)+1,2**(level+1)*grid)


def _near_slots(c,pop,point):
    face,level,x,y=c.baseline['physical_address'];_,u,v,den=chart(point,face);grid=1
    if den<=0:return
    while grid*grid<pop['founder_count']:grid*=2
    salt=int(checksum([pop['population_id'],'position'])[:16],16);mod=grid*grid;mult=2*(salt//mod)+1
    inverse=pow(mult,-1,mod) if mod>1 else 0;ix=u*2**level*grid//den-x*grid;iy=v*2**level*grid//den-y*grid
    for j in range(max(0,iy-1),min(grid,iy+2)):
        for i in range(max(0,ix-1),min(grid,ix+2)):
            slot=((j*grid+i-salt)*inverse)%mod if mod>1 else 0
            if slot<pop['founder_count']:yield slot


def _packet(db,cid,target,v,p,point,minute,rows,cache):
    runtime=db.info.get(('L2_batch',cid))
    if runtime is not None:return runtime.packet(target,point,minute,rows,cache)
    candidates=[]
    for source in rows:
        if source.species_id!=target.species_id:continue
        # All source rows were checked/produced under advance's writer fence.
        # Rehashing every cohort for every packet is quadratic in population size.
        d=source.data;c=_entity(db,cid,Community,source.community_id,v)
        pop=next(x for x in c.baseline['populations'] if x['species_id']==source.species_id)
        for bank_index,bank in enumerate(d['bank']):
            if not bank['remaining'] or bank['expires']<=minute:continue
            cohort=bank['cohort'];kids={x['slot']:x for x in cohort['mature_children']};excluded=set(cohort['excluded_founders'])
            for slot in _near_slots(c,pop,point):
                child=kids.get(slot)
                if child:parent_id=child['id'];position=SurfacePoint(*child['point'])
                elif not cohort['all_founders_dead'] and slot not in excluded:
                    parent_id='vgi:'+checksum([pop['population_id'],slot])[:32];position=_slot_point(c,pop,slot)
                else:continue
                if bank['used'].get(parent_id,0)>=bank['per_parent']:continue
                distance=distance_m(v.environment.regional.terrain.plan.source.config,point,position)
                if distance>d['profile']['dispersal_m']:continue
                candidates.append((distance,source.population_id,bank_index,parent_id,list(position.xyz),source))
    from .service import eligibility_at
    for distance,popid,index,parent_id,position,source in sorted(candidates,key=lambda x:x[:4]):
        key=(source.species_id,tuple(position))
        if key not in cache:
            q=SurfacePoint(*position);cache[key]=eligibility_at(db,cid,v,v.catalog.species[source.species_id],q)[0]=='eligible'
        if cache[key]:
            if source.data['profile'].get('sexual_policy_revision'):
                from .sexual import compatible_mate
                if compatible_mate(db,source,source.data['bank'][index],parent_id,position,v,cache) is None:continue
            return source,index,parent_id,position
    return None


def _recruit(db,cid,row,rows,v,p,minute,cache):
    _check(row);d=row.data
    if d['profile']['blocked_reason']:return
    native=_native(db,cid,row.population_id);c=_entity(db,cid,Community,row.community_id,v);sp=v.catalog.species[row.species_id]
    pop=next(x for x in c.baseline['populations'] if x['species_id']==row.species_id)
    slots=set(map(int,d['vacancies']))
    if d['all_dead_at'] is not None:
        # Bounded hierarchical probes of a completely cleared implicit population.
        # This is an attempt budget, not a quota of successful plants.
        for i in range(min(64,d['capacity'])):slots.add(int(checksum([row.population_id,minute,i,'clear_probe'])[:16],16)%d['capacity'])
    chance=d['profile']['establishment_chance_ppm']
    for slot in sorted(slots):
        entry=native.data['slots'].get(str(slot),{})
        if entry.get('occupant') or entry.get('reservation'):continue
        death=d['vacancies'].get(str(slot),d['all_dead_at'])
        if death is None or death>=minute:continue
        if int(checksum([p.signature,row.population_id,slot,minute,'establishment'])[:16],16)%Q>=chance:continue
        point=_slot_point(c,pop,slot)
        packet=_packet(db,cid,row,v,p,point,minute,rows,cache)
        if packet is None:continue
        source,index,parent_id,parent_point=packet
        sd=deepcopy(source.data);bank=sd['bank'][index];mass=bank['unit_mass_mg']
        bank['remaining']-=1;bank['used'][parent_id]=bank['used'].get(parent_id,0)+1;sd['ledger']['attempts']+=1
        # Both the biological origin and the canonical target microsite are checked.
        try:b=service._individual_baseline(v,c,row.species_id,slot)
        except ValueError as exc:
            if 'microsite unsupported' not in str(exc):raise
            sd['ledger']['failed_mg']+=mass;_put(source,sd);continue
        due=life.time_for_work(minute,14*DAY*Q,life.rates(v,b,sp),life_profile(sp)['growth_seasons'])
        if due is None or due>bank['expires']:
            sd['ledger']['failed_mg']+=mass;_put(source,sd);continue
        b=resources.founding_baseline(db,cid,v,b,None)
        # Preserve the canonical founder tombstone, materializing only involved slots.
        # An unobserved founder tombstone is already authoritative in slot occupancy
        # and the disturbance receipt. Do not create geological/E1 probes for it.
        target_dead_id=b['individual_id']
        eid='vl2:'+checksum([p.signature,row.population_id,slot,minute])[:32]
        payload={'version':1,'parent_id':parent_id,'parent_point':parent_point,'target_dead_id':target_dead_id,'species_id':sp.id,
            'part_id':None,'escrow_mass_mg':mass,'created_minute':minute,'target_baseline':deepcopy(b),'slot':slot,
            'child_id':'vgi:l2:'+checksum([eid,parent_id])[:32],'propagation':d['profile']['mechanism'],
            'signature':life.header(db,cid,v).signature,'renewal_signature':p.signature,
            'source_account':{'population_id':source.population_id,'bank_id':bank['id'],'produced_minute':bank['created'],
                'expires_minute':bank['expires'],'parent_alive_at_production':True,'modeled_assimilation_not_R1_harvest_mass':True}}
        if source.data['profile'].get('sexual_policy_revision'):
            payload['sexual_authorization']=cache[('S1_mate',source.population_id,bank['id'],parent_id)]
            payload['target_baseline']['sexual_policy_signature']=source.data['profile']['sexual_policy_signature']
        event=Event(campaign_id=cid,event_id=eid,population_id=row.population_id,due_minute=due,status='pending',payload=payload,payload_checksum=checksum(payload))
        db.add(event);nd=deepcopy(native.data);nd['slots'][str(slot)]={'dead_founder':True,'occupant':None,'reservation':eid};life._popwrite(native,nd)
        sd['ledger']['dispersed_mg']+=mass;sd['ledger']['birth_events']+=1;_put(source,sd)
    db.flush()


def advance(db,cid,v=None):
    if db.info.get(('L2_advancing',cid)):return
    v=v or service.context(db,cid);p=header(db,cid,v)
    if p is None:return
    if p.descriptor['kind']=='vegetation_renewal_ga2':
        from .renewal_gameplay import advance_ga2
        return advance_ga2(db,cid,v,p)
    if not db.info.get(('L2_reference',cid)):
        from .renewal_batch import advance_batch
        return advance_batch(db,cid,v,p)
    end=life.now(db,cid)
    if end<p.last_minute:raise ValueError('L2 ecological time cannot move backwards')
    if end==p.last_minute:return
    service._fence(db,cid)
    with db.begin_nested(),db.no_autoflush:
        p=header(db,cid,v);start=p.last_minute
        db.info[('L2_advancing',cid)]=True
        db.info[('L2_entities',cid)]={}
        try:
            rows=list(db.query(Renewing).filter_by(campaign_id=cid).order_by(Renewing.population_id));cache={}
            for minute in rounds(start,end):
                for row in rows:life.process_events(db,cid,row.population_id,v,_until=minute)
                for row in rows:_produce(db,cid,row,v,p,minute)
                for row in rows:_recruit(db,cid,row,rows,v,p,minute,cache)
            for row in rows:life.process_events(db,cid,row.population_id,v,_until=end)
            p.last_minute=end;p.state_checksum=checksum([p.signature,end]);db.flush()
        finally:
            db.info.pop(('L2_advancing',cid),None);db.info.pop(('L2_entities',cid),None)


def before_sync(db,cid,row,v):
    p=header(db,cid,v)
    if p is None:
        if row.baseline.get('renewal_signature'):raise ValueError('Missing L2 authority')
        return
    if row.baseline.get('renewal_signature') not in (None,p.signature):raise ValueError('L2 child authority mismatch')
    if row.baseline.get('sexual_policy_signature'):
        from .sexual import validate_profile
        validate_profile(db,cid,row.baseline)
    if not db.info.get(('L2_advancing',cid)):advance(db,cid,v)
    c=db.get(Community,(cid,row.community_id))
    watch(db,cid,c,row.baseline['species_id'],v,p)
    native=db.get(Population,(cid,row.baseline['population_id']))
    if native is None:return
    entry=native.data['slots'].get(str(row.baseline['slot']),{})
    if row.baseline.get('birth_event_id') is None and (entry.get('dead_founder') or native.data.get('cleared_minute') is not None) and row.state['alive']:
        s=deepcopy(row.state);life.kill_state(s)
        tracked=db.get(Renewing,(cid,row.baseline['population_id']))
        death=(tracked.data['founder_deaths'].get(str(row.baseline['slot']),tracked.data['founders_cleared_at']) if tracked else native.data.get('cleared_minute'))
        if death is None:death=tracked.data['vacancies'].get(str(row.baseline['slot'])) if tracked else None
        s['life'].update(death_recorded=True,death_minute=death);life._store(row,s)


def on_death(db,cid,row,v):
    p=header(db,cid,v)
    if p is None:return False
    c=db.get(Community,(cid,row.community_id));r=watch(db,cid,c,row.baseline['species_id'],v,p)
    d=deepcopy(r.data);d['vacancies'][str(row.baseline['slot'])]=life.now(db,cid);_put(r,d)
    if row.baseline.get('birth_event_id') is None:
        d=deepcopy(r.data);d['founder_deaths'].setdefault(str(row.baseline['slot']),life.now(db,cid));_put(r,d)
    # Register compatible nearby source populations at the explicit disturbance.
    from ..geology.regional.experiment import window_point
    radius=parse_config(p.descriptor['config']).internal_dispersal_m;center=SurfacePoint(*row.baseline['point'])
    queries={v.address(q)[1]:q for q in (window_point(center,x,y,v.radius) for x in (-radius,0,radius) for y in (-radius,0,radius))}
    for identifier,q in sorted(queries.items()):
        if identifier==row.community_id:continue
        if row.baseline['species_id'] not in {x['species_id'] for x in service.sample_initial_community(db,cid,v,q)['populations']}:continue
        other=service.materialize_community(db,cid,q);watch(db,cid,other,row.baseline['species_id'],v,p)
    return True


def on_clear(db,cid,community_id,sid,v):
    p=header(db,cid,v)
    if p is None:return
    c=db.get(Community,(cid,community_id));r=watch(db,cid,c,sid,v,p);d=deepcopy(r.data)
    d['all_dead_at']=life.now(db,cid);d['vacancies']={}
    if d['founders_cleared_at'] is None:d['founders_cleared_at']=life.now(db,cid)
    for b in d['bank']:d['ledger']['expired_mg']+=b['remaining']*b['unit_mass_mg']
    d['bank']=[];_put(r,d)


def _register_border_sources(db,cid,c,sid,v,p):
    from ..geology.regional.experiment import window_point
    face,level,x,y=c.baseline['physical_address'];radius=parse_config(p.descriptor['config']).internal_dispersal_m
    probes={}
    for i,j in ((0,0),(0,1),(0,2),(1,0),(1,2),(2,0),(2,1),(2,2)):
        edge=point_on_face(face,2*x+i,2*y+j,2**(level+1))
        for dx in (-radius,0,radius):
            for dy in (-radius,0,radius):
                q=window_point(edge,dx,dy,v.radius);probes[v.address(q)[1]]=q
    for identifier,q in sorted(probes.items()):
        if identifier==c.community_id:continue
        if sid not in {x['species_id'] for x in service.sample_initial_community(db,cid,v,q)['populations']}:continue
        other=service.materialize_community(db,cid,q);watch(db,cid,other,sid,v,p)


def disturb_population(db,cid,community_id,sid,count,key,*,experimental=False,sterilize_bank=False,_selected_slots=None):
    """Trusted ecological disturbance: finite sparse mortality, no inventory output.

    Used by developer proofs; no public endpoint accepting player assertions.
    """
    if experimental is not True or type(count)is not int or count<1 or not isinstance(key,str) or not 1<=len(key)<=128:
        raise ValueError('Explicit bounded experimental disturbance required')
    v=service.context(db,cid);p=header(db,cid,v)
    if p is None:raise ValueError('Explicit L2 required')
    request=[community_id,sid,count,sterilize_bank]
    if _selected_slots is not None:
        if (type(_selected_slots)is not list or len(_selected_slots)!=count or any(type(s)is not int or s<0 for s in _selected_slots) or len(set(_selected_slots))!=count):
            raise ValueError('Explicit disturbance slots must be unique nonnegative integers matching count')
        request.append(list(_selected_slots))
    eid='vl2dist:'+checksum([p.signature,key])[:32];old=db.get(Event,(cid,eid))
    if old:
        if checksum(old.payload)!=old.payload_checksum or old.payload['request']!=request:raise ValueError('L2 disturbance key collision')
        return old
    service._fence(db,cid)
    with db.begin_nested():
        advance(db,cid,v);c=db.get(Community,(cid,community_id));r=watch(db,cid,c,sid,v,p)
        _register_border_sources(db,cid,c,sid,v,p)
        native=_native(db,cid,r.population_id)
        if count>r.data['capacity']:raise ValueError('Mortality exceeds physical capacity')
        if _selected_slots is not None and max(_selected_slots)>=r.data['capacity']:raise ValueError('Disturbance slot outside physical capacity')
        nd=deepcopy(native.data);d=deepcopy(r.data);capacity=d['capacity'];salt=int(checksum([p.signature,r.population_id,key])[:16],16)
        mul=2*(salt//capacity)+1
        while gcd(mul,capacity)!=1:mul+=2
        chosen=[(i*mul+salt)%capacity for i in range(count)] if count<capacity else None
        if _selected_slots is not None and count<capacity:chosen=list(_selected_slots)
        if chosen is None:
            nd['cleared_minute']=life.now(db,cid);d['all_dead_at']=life.now(db,cid)
            if d['founders_cleared_at'] is None:d['founders_cleared_at']=life.now(db,cid)
            chosen=list(map(int,nd['slots']))
        else:
            for slot in chosen:
                d['vacancies'][str(slot)]=life.now(db,cid)
                d['founder_deaths'].setdefault(str(slot),life.now(db,cid))
        selected=set(chosen)
        for slot in chosen:
            previous=nd['slots'].get(str(slot),{});reservation=previous.get('reservation')
            if previous.get('ga2_child'):
                from .renewal_gameplay import retire_compact
                retire_compact(nd,previous,life.now(db,cid))
            if reservation:
                e=db.get(Event,(cid,reservation));e.status='cancelled_disturbance'
            nd['slots'][str(slot)]={'dead_founder':True,'occupant':None,'reservation':None}
        for ind in db.query(Individual).filter_by(campaign_id=cid,community_id=community_id):
            if ind.baseline['species_id']!=sid or (count<capacity and ind.baseline['slot'] not in selected):continue
            s=deepcopy(ind.state)
            if s['alive']:life.kill_state(s)
            s['life'].update(death_recorded=True,death_minute=life.now(db,cid));life._store(ind,s)
        if sterilize_bank:
            for b in d['bank']:d['ledger']['expired_mg']+=b['remaining']*b['unit_mass_mg']
            d['bank']=[]
        life._popwrite(native,nd);_put(r,d)
        payload={'kind':'L2_disturbance','request':request,'minute':life.now(db,cid),'selected_slots':chosen if count<capacity else 'all',
            'signature':p.signature,'capacity':capacity,'removed_slots':count,'reason':'explicit_experimental_ecological_disturbance'}
        row=Event(campaign_id=cid,event_id=eid,population_id=r.population_id,due_minute=life.now(db,cid),status='disturbance_applied',payload=payload,payload_checksum=checksum(payload))
        db.add(row);db.flush();return row


def query_population(db,cid,community_id,sid):
    p=db.get(Plan,cid)
    if p is not None and p.descriptor['kind']=='vegetation_renewal_ga2':
        from .renewal_gameplay import query_population_ga2
        return query_population_ga2(db,cid,community_id,sid)
    if not db.info.get(('L2_reference',cid)):
        from .renewal_batch import query_population_batch
        return query_population_batch(db,cid,community_id,sid)
    v=service.context(db,cid)
    if header(db,cid,v) is None:raise ValueError('Explicit L2 required')
    advance(db,cid,v);c=db.get(Community,(cid,community_id));r=watch(db,cid,c,sid,v);_check(r)
    service._physical_current(db,cid,c)
    pop=next(x for x in c.baseline['populations'] if x['species_id']==sid)
    count,fraction=life.population_counts(db,cid,c,pop,v)
    children=[x for x in db.query(Individual).filter_by(campaign_id=cid,community_id=community_id) if x.baseline['species_id']==sid and x.baseline.get('birth_event_id') and x.state['alive']]
    stages={'germinating':0,'young':0,'adult':0}
    for child in children:stages[child.state['life']['maturity']]+=1
    stages['adult']+=count-len(children)
    return {'renewal_version':2,'population_id':r.population_id,'capacity':r.data['capacity'],'living_count':count,'stages':stages,
        'cover_fraction_ppm':fraction,'bank_packets':sum(b['remaining'] for b in r.data['bank'] if b['expires']>life.now(db,cid)),
        'ledger':deepcopy(r.data['ledger']),'profile':r.data['profile'],'children':[{'id':x.individual_id,'birth_minute':x.state['life']['birth_minute'],
            'height_cm':x.state['life']['height_cm'],'maturity':x.state['life']['maturity']} for x in children]}
