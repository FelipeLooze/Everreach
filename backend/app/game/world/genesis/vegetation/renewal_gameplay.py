"""GA2: finite time-rated recruitment, sparse opportunities and lazy bodies.

Births persist in L2's events and native slot occupancy. Unencountered children
have immutable identity/phenotype records, not thousands of ORM/resource bodies.
GA1 remains the sole growth clock. No habitat, R1 stock or water is invented.
"""
from copy import deepcopy
import heapq
from typing import Literal

from pydantic import Field, field_validator
from sqlalchemy import event

from . import renewal as l2, lifecycle as life, service, resources
from .renewal_batch import Runtime
from .growth_gameplay import LifeConfigGA1, pacing_class, attach_profile
from .life_math import DAY, YEAR, Q, NAMES, work, time_for_work
from ..sphere_topology import SurfacePoint
from ..terrain.field import checksum


INTERVALS={'flower_herb':[3,5],'shrub':[5,10],'tree':[7,14],
           'large_tree':[10,15],'slow_tree':[10,15],'other':[5,12],'legacy':[10,20]}
ESTABLISH={'flower_herb':[1,3],'shrub':[2,5],'tree':[3,7],
           'large_tree':[3,7],'slow_tree':[3,7],'other':[2,5],'legacy':[3,7]}
ANNUAL={'flower_herb':60,'shrub':36,'tree':24,'large_tree':18,'slow_tree':18,'other':30,'legacy':0}
SUCCESS={'flower_herb':350000,'shrub':250000,'tree':180000,
         'large_tree':120000,'slow_tree':120000,'other':200000,'legacy':0}


class RenewalConfigGA2(l2.RenewalConfigL2):
    renewal_policy: Literal['adventure_renewal_ga2']='adventure_renewal_ga2'
    intervals_days: dict[str,list[int]]=Field(default_factory=lambda:deepcopy(INTERVALS))
    establishment_days_by_class: dict[str,list[int]]=Field(default_factory=lambda:deepcopy(ESTABLISH))
    annual_packets_per_adult: dict[str,int]=Field(default_factory=lambda:dict(ANNUAL))
    success_ppm: dict[str,int]=Field(default_factory=lambda:dict(SUCCESS))
    viability_days: int=Field(default=30,ge=8,le=180)
    seasonal_floor_ppm: int=Field(default=750000,ge=500000,le=1000000)

    @field_validator('annual_reserve_ppm')
    @classmethod
    def legacy_mass_knob(cls,value):
        if value!=1000:raise ValueError('GA2 uses annual_packets_per_adult; legacy L2 mass ppm is not a GA2 tuning knob')
        return value

    @field_validator('intervals_days','establishment_days_by_class')
    @classmethod
    def bands(cls,v):
        if set(v)!=set(INTERVALS):raise ValueError('GA2 requires all pacing classes')
        for bounds in v.values():
            if len(bounds)!=2 or any(type(n)is not int for n in bounds) or not 1<=bounds[0]<=bounds[1]<=30:
                raise ValueError('Invalid GA2 day band')
        return v

    @field_validator('annual_packets_per_adult','success_ppm')
    @classmethod
    def counts(cls,v,info):
        limit=360 if info.field_name=='annual_packets_per_adult' else Q
        if set(v)!=set(INTERVALS) or any(type(n)is not int or not 0<=n<=limit for n in v.values()):
            raise ValueError('Invalid GA2 finite rate')
        return v


def rules():
    return {'policy':'adventure_renewal_ga2','revision':1,'engine_version':2,
            'clock':'official_game_calendar_population_phase_from_activation',
            'budget':'integral_mature_producer_minutes_times_annual_rate_v1',
            'overflow':'discard_whole_unminted_tokens_keep_fraction_only',
            'parts':'no_R1_debit_or_inventory_items',
            'birth':'finite_event_reserved_slot_immutable_phenotype_v1',
            'lazy':'unencountered_bodies_stay_compact_no_visit_chances',
            'registration':'participants_disturbance_and_real_border_sources_only',
            'habitat':'unchanged_Vg2_eligibility_and_S1_authorization',
            'full_clear_probes':64,'position':'canonical_slot_point',
            'growth':'unchanged_GA1','rarity':'success_and_dispersal_not_months_of_cadence'}


def initialize_ga2(db,cid,config=None,*,experimental=False):
    if experimental is not True:raise ValueError('Explicit experimental GA2 activation required')
    v=service.context(db,cid);lp=life.header(db,cid,v)
    if lp is None or not isinstance(life.parse_config(lp.descriptor['config']),LifeConfigGA1):
        raise ValueError('GA2 requires explicitly initialized GA1')
    cfg=config or RenewalConfigGA2()
    old=l2.header(db,cid,v)
    if old:
        if old.descriptor['config']!=cfg.model_dump(mode='json'):raise ValueError('Cannot reconfigure L2/GA2')
        return old
    if db.query(l2.Event).filter_by(campaign_id=cid,status='pending').first():
        raise ValueError('GA2 activation requires explicit resolution of pending legacy L1 events')
    if any(r.baseline.get('birth_event_id') for r in db.query(l2.Individual).filter_by(campaign_id=cid)):
        raise ValueError('GA2 does not silently convert existing legacy offspring')
    service._fence(db,cid)
    with db.begin_nested():
        p=l2.initialize_renewal(db,cid,cfg,experimental=True)
        from .sexual import initialize_sexual_policy
        initialize_sexual_policy(db,cid,experimental=True)
        return p


def choose(spid,domain,bounds):
    low,high=bounds
    return low+int(checksum([spid,'GA2',domain])[:8],16)%(high-low+1)


def configure_profile(profile,sp,growth_config,cfg):
    kind=pacing_class(sp,growth_config)
    interval=choose(sp.id,'interval',cfg.intervals_days[kind])*DAY
    establish=choose(sp.id,'establish',cfg.establishment_days_by_class[kind])*DAY
    rarity={'comum':1000,'incomum':850,'raro':700,'muito_raro':550,'excepcional':0}[life.life_profile(sp)['rarity']]
    # Legacy mass-reference fields stay readable for L2 diagnostics. GA2 mints
    # only by the explicit token/time budget below, never by that quarterly quota.
    return {**profile,'renewal_policy':'adventure_renewal_ga2','pacing_class':kind,
            'opportunity_interval_minutes':interval,'establishment_minutes':establish,
            'annual_packets_per_mature_adult':cfg.annual_packets_per_adult[kind],
            'packets_per_adult_per_period':max(1,(cfg.annual_packets_per_adult[kind]*interval+YEAR-1)//YEAR),
            'establishment_chance_ppm':cfg.success_ppm[kind]*rarity//1000,
            'GA2_viability_minutes':cfg.viability_days*DAY}


def seasonal_rates(sp,cfg):
    preferred=life.life_profile(sp)['growth_seasons']
    return [Q if NAMES[i] in preferred or 'todo_ano_condicionado_a_atividade_biologica' in preferred
            else cfg.seasonal_floor_ppm for i in range(4)]


def opportunities(row,activation,start,end):
    step=row.data['profile']['opportunity_interval_minutes']
    phase=1+int(checksum([row.population_id,'GA2_phase'])[:12],16)%(step//DAY)
    first=activation+phase*DAY
    k=max(0,(start-first)//step+1)
    while first+k*step<=end:
        yield first+k*step
        k+=1


def schedule(rows,p,start,end):
    heap=[];iterators={}
    for row in rows:
        it=iter(opportunities(row,p.descriptor['activation_minute'],start,end));iterators[row.population_id]=it
        t=next(it,None)
        if t is not None:heapq.heappush(heap,(t,row.population_id,row))
    while heap:
        minute=heap[0][0];due=[]
        while heap and heap[0][0]==minute:
            _,key,row=heapq.heappop(heap);due.append(row)
            t=next(iterators[key],None)
            if t is not None:heapq.heappush(heap,(t,key,row))
        yield minute,due


def stage_record(record,minute):
    if minute<record['birth_minute']:raise ValueError('GA2 child queried before birth')
    p=record['profile'];age=work(record['birth_minute'],minute,record['growth_rates_ppm'],p['growth_seasons'])
    mature=p['mature_active_days']*DAY*Q;germ=p['germination_active_days']*DAY*Q
    return {'height_cm':max(1,record['height_cm']*min(age,mature)//mature),
            'maturity':'germinating' if age<germ else 'young' if age<mature else 'adult',
            'birth_minute':record['birth_minute']}


def checked_record(entry):
    record=entry['ga2_child']
    if checksum(record)!=entry['ga2_child_checksum'] or record['individual_id']!=entry['occupant']:
        raise ValueError('GA2 compact occupant corrupted')
    return record


def retire_compact(native_data,entry,minute):
    r=checked_record(entry)
    deaths=dict(native_data.get('ga2_deaths',{}));deaths[r['individual_id']]=minute
    native_data['ga2_deaths']=deaths
    entry.pop('ga2_child',None);entry.pop('ga2_child_checksum',None)


class GA2Runtime(Runtime):
    def __init__(self,db,cid,v,p):
        super().__init__(db,cid,v,p)
        self.config=l2.parse_config(p.descriptor['config'])
        self.life_plan=life.header(db,cid,self.v)
        self.life_config=life.parse_config(self.life_plan.descriptor['config'])
        self.bodies={r.individual_id:r for r in db.query(l2.Individual).filter_by(campaign_id=cid)}
        self.site_cache={};self.processed_rounds=0
        self.compact_cache={};self.cohort_cache={};self.cohort_builds=0

    def compact(self,entry):
        rec=entry['ga2_child'];key=entry['occupant']
        previous=self.compact_cache.get(key)
        if previous is not None and previous[0] is rec and previous[1]==entry['ga2_child_checksum']:return rec
        rec=checked_record(entry);self.compact_cache[key]=(rec,entry['ga2_child_checksum']);return rec

    def mate_cohort(self,bank):
        if bank['id'] not in self.cohorts:
            c=bank['cohort'];self.cohorts[bank['id']]=(c['all_founders_dead'],set(c['excluded_founders']),{x['slot']:x for x in c['mature_children']})
        return self.cohorts[bank['id']]

    def cohort(self,row,minute):
        native=self.native(row.population_id);c=l2._entity(self.db,self.cid,l2.Community,row.community_id,self.v)
        pop=next(p for p in c.baseline['populations'] if p['species_id']==row.species_id)
        cached=self.cohort_cache.get(row.population_id)
        if cached is not None and cached[0] is native.data and minute<cached[1]:return cached[2]
        self.cohort_builds+=1
        children=[];times=[];slots=native.data['slots'];next_maturity=float('inf')
        for slot,entry in slots.items():
            if not entry.get('occupant'):continue
            if entry.get('ga2_child'):
                rec=self.compact(entry);at=rec['mature_minute'];body=self.bodies.get(entry['occupant'])
                if body is not None and not body.state['alive']:raise ValueError('GA2 dead body occupies a live slot')
                if at<=minute:children.append({'slot':int(slot),'id':entry['occupant'],'point':rec['point']});times.append(at)
                else:next_maturity=min(next_maturity,at)
            else:
                body=self.bodies.get(entry['occupant'])
                if body is None:raise ValueError('GA2 missing pre-existing body')
                if self.adult(body,minute):
                    from .life_math import maturity_minute
                    at=maturity_minute(body.state['life']);times.append(at)
                    children.append({'slot':int(slot),'id':body.individual_id,'point':body.baseline['point']})
        cleared=native.data.get('cleared_minute') is not None
        founders=0 if cleared else pop['founder_count']-len(slots)
        result=({'founder_capacity':pop['founder_count'],'all_founders_dead':cleared,
                'excluded_founders':sorted(map(int,slots)),'mature_children':children,
                'adults':founders+len(children)},founders,times)
        self.cohort_cache[row.population_id]=(native.data,next_maturity,result)
        return result

    def produce(self,row,minute):
        d=deepcopy(row.data);profile=d['profile'];ledger=d['ledger'];kept=[]
        for bank in d['bank']:
            if bank['expires']<=minute:ledger['expired_mg']+=bank['remaining']*bank['unit_mass_mg']
            else:kept.append(bank)
        d['bank']=kept
        marks=dict(d.get('ga2_marks',{}));marks.setdefault('first_opportunity_minute',minute);d['ga2_marks']=marks
        previous=d.get('ga2_last_production_minute',self.p.descriptor['activation_minute'])
        d['ga2_last_production_minute']=minute
        if profile['blocked_reason'] or not profile['annual_packets_per_mature_adult']:
            self.stage(row,d);return
        if minute<profile.get('sexual_effective_minute',minute):self.stage(row,d);return
        previous=max(previous,profile.get('sexual_effective_minute',previous))
        cohort,founders,maturity_times=self.cohort(row,minute);adults=cohort['adults']
        budget=dict(d.get('ga2_budget',{'remainder':0,'earned_tokens':0,'discarded_tokens':0,'producer_work_ppm_minutes':0}))
        sp=self.v.catalog.species[row.species_id];seasonal=seasonal_rates(sp,self.config)
        produced_work=founders*work(previous,minute,seasonal)
        produced_work+=sum(work(max(previous,t),minute,seasonal) for t in maturity_times if t<minute)
        denominator=YEAR*Q
        earned,remainder=divmod(budget['remainder']+produced_work*profile['annual_packets_per_mature_adult'],denominator)
        budget['remainder']=remainder;budget['earned_tokens']+=earned;budget['producer_work_ppm_minutes']+=produced_work
        room=max(0,adults*self.config.bank_packets_per_adult-sum(b['remaining'] for b in kept))
        if profile.get('sexual_policy_revision') and adults<profile['minimum_mature_producers']:room=0
        amount=min(room,earned);budget['discarded_tokens']+=earned-amount;d['ga2_budget']=budget
        if amount:
            bid='ga2bank:'+checksum([self.p.signature,row.population_id,minute])[:32]
            d['bank'].append({'id':bid,'created':minute,'expires':minute+profile['GA2_viability_minutes'],
                              'produced':amount,'remaining':amount,'unit_mass_mg':profile['unit_mass_mg'],
                              'per_parent':profile['packets_per_adult_per_period'],'used':{},'cohort':cohort,
                              'origin_population_id':row.population_id,'reserve_is_modeled':True})
            ledger['produced_mg']+=amount*profile['unit_mass_mg'];ledger['produced_packets']+=amount
            marks.setdefault('first_propagule_minute',minute)
        self.stage(row,d)

    def site(self,row,pop,c,slot,cache):
        key=(row.population_id,slot)
        if key not in self.site_cache:
            from .service import eligibility_at, microenvironment_context
            point=l2._slot_point(c,pop,slot);sp=self.v.catalog.species[row.species_id]
            local=microenvironment_context(self.db,self.cid,self.v,point)
            okay=eligibility_at(self.db,self.cid,self.v,sp,point,_local_context=local)[0]=='eligible';cache[(row.species_id,tuple(point.xyz))]=okay
            self.site_cache[key]=(point,life.rates(self.v,{'point':list(point.xyz),'microenvironment_context':local},sp)) if okay else None
        return self.site_cache[key]

    def recruit(self,row,minute,cache):
        d=row.data;profile=d['profile']
        if profile['blocked_reason']:return
        native=self.native(row.population_id);c=l2._entity(self.db,self.cid,l2.Community,row.community_id,self.v)
        pop=next(x for x in c.baseline['populations'] if x['species_id']==row.species_id)
        slots=set(map(int,d['vacancies']))
        if d['all_dead_at'] is not None:
            for i in range(min(64,d['capacity'])):slots.add(int(checksum([row.population_id,minute,i,'GA2_clear_probe'])[:16],16)%d['capacity'])
        for slot in sorted(slots):
            entry=native.data['slots'].get(str(slot),{})
            if entry.get('occupant') or entry.get('reservation'):continue
            death=d['vacancies'].get(str(slot),d['all_dead_at'])
            if death is None or death>=minute:continue
            if int(checksum([self.p.signature,row.population_id,slot,minute,'GA2_establish'])[:16],16)%Q>=profile['establishment_chance_ppm']:continue
            site=self.site(row,pop,c,slot,cache)
            if site is None:continue
            point,environmental_rates=site
            packet=self.packet(row,point,minute,self.rows,cache)
            if packet is None:continue
            source,index,parent_id,parent_point=packet;sd=deepcopy(source.data);bank=sd['bank'][index]
            due=minute+profile['establishment_minutes'];mass=bank['unit_mass_mg']
            bank['remaining']-=1;bank['used'][parent_id]=bank['used'].get(parent_id,0)+1;sd['ledger']['attempts']+=1
            if due>bank['expires']:
                sd['ledger']['failed_mg']+=mass;self.stage(source,sd);continue
            eid='vga2:'+checksum([self.p.signature,row.population_id,slot,minute])[:32]
            child_id='vgi:ga2:'+checksum([eid,parent_id])[:32]
            sp=self.v.catalog.species[row.species_id]
            growth_profile,growth_rates=attach_profile(sp,self.life_config,{'individual_id':child_id},environmental_rates)
            if growth_rates is None:raise ValueError('GA2 cannot silently authorize exceptional growth')
            record={'version':1,'individual_id':child_id,'community_id':row.community_id,
                    'population_id':row.population_id,'species_id':row.species_id,'slot':slot,'point':list(point.xyz),
                    'height_cm':pop['height_cm'],'birth_minute':due,'birth_event_id':eid,'parent_id':parent_id,
                    'profile':growth_profile,'rates':environmental_rates,'growth_rates_ppm':growth_rates,
                    'mature_minute':time_for_work(due,growth_profile['mature_active_days']*DAY*Q,growth_rates,growth_profile['growth_seasons']),
                    'escrow_mass_mg':mass,'renewal_signature':self.p.signature,'life_signature':self.life_plan.signature}
            payload={'version':1,'ga2_signature':self.p.signature,'signature':self.life_plan.signature,
                     'renewal_signature':self.p.signature,'child_id':child_id,'slot':slot,'species_id':sp.id,
                     'parent_id':parent_id,'parent_point':parent_point,'part_id':None,'escrow_mass_mg':mass,
                     'created_minute':minute,'ga2_child':record,'ga2_child_checksum':checksum(record),
                     'source_account':{'population_id':source.population_id,'bank_id':bank['id'],
                                       'produced_minute':bank['created'],'expires_minute':bank['expires'],
                                       'parent_alive_at_production':True,'not_R1_harvest_mass':True}}
            if source.data['profile'].get('sexual_policy_revision'):
                payload['sexual_authorization']=cache[('S1_mate',source.population_id,bank['id'],parent_id)]
            self.db.add(l2.Event(campaign_id=self.cid,event_id=eid,population_id=row.population_id,due_minute=due,
                                status='pending',payload=payload,payload_checksum=checksum(payload)))
            nd=deepcopy(native.data);nd['slots'][str(slot)]={'dead_founder':True,'occupant':None,'reservation':eid}
            self.stage(native,nd,True);sd['ledger']['dispersed_mg']+=mass;sd['ledger']['birth_events']+=1;self.stage(source,sd)

    def birth(self,e,until):
        if not e.payload.get('ga2_signature'):return super().birth(e,until)
        x=e.payload
        if checksum(x)!=e.payload_checksum or x['ga2_signature']!=self.p.signature or x['signature']!=self.life_plan.signature:
            raise ValueError('GA2 birth event authority corrupted')
        if x.get('sexual_authorization'):
            from .sexual import validate_profile
            validate_profile(self.db,self.cid,{'sexual_policy_signature':x['sexual_authorization']['policy_signature']})
        record=x['ga2_child']
        if checksum(record)!=x['ga2_child_checksum'] or record['birth_minute']!=e.due_minute:
            raise ValueError('GA2 birth phenotype corrupted')
        native=self.native(e.population_id);nd=deepcopy(native.data);slot=dict(nd['slots'][str(x['slot'])])
        if slot['reservation']!=e.event_id or slot['occupant']:raise ValueError('GA2 reservation mismatch')
        # Habitat was checked at this exact, immutable canonical point before reserving.
        slot.update(occupant=x['child_id'],reservation=None,ga2_child=record,ga2_child_checksum=x['ga2_child_checksum'])
        nd['slots'][str(x['slot'])]=slot;self.stage(native,nd,True);e.status='established'
        row=next(r for r in self.rows if r.population_id==e.population_id)
        d=deepcopy(row.data);d['vacancies']=dict(d['vacancies']);d['vacancies'].pop(str(x['slot']),None)
        marks=dict(d.get('ga2_marks',{}));marks.setdefault('first_birth_minute',e.due_minute);d['ga2_marks']=marks
        self.stage(row,d)


def catch_up_full(db,cid,row,v,p,start,end):
    """Bounded to registered full cohorts; no child or visit-triggered recruitment."""
    if end<=start:return
    # The ordinary scheduler will replay these same fixed opportunities. This path
    # exists only for a newly registered, historically undisturbed full population.
    runtime=GA2Runtime(db,cid,v,p)
    db.info[('L2_batch',cid)]=runtime
    try:
        for minute in opportunities(row,start,start,end):runtime.produce(row,minute)
        runtime.close();db.flush()
    finally:db.info.pop(('L2_batch',cid),None)


def advance_ga2(db,cid,v,p):
    end=life.now(db,cid)
    if end<p.last_minute:raise ValueError('GA2 time cannot move backwards')
    if end==p.last_minute:return
    service._fence(db,cid)
    with db.begin_nested(),db.no_autoflush:
        p=l2.header(db,cid,v);end=life.now(db,cid)
        if end<p.last_minute:raise ValueError('GA2 time cannot move backwards under the writer fence')
        if end==p.last_minute:return
        runtime=GA2Runtime(db,cid,v,p)
        db.info[('L2_advancing',cid)]=True;db.info[('L2_entities',cid)]={};db.info[('L2_batch',cid)]=runtime
        event.listen(db,'before_flush',runtime.finalize)
        try:
            cache={}
            for minute,due_rows in schedule(runtime.rows,p,p.last_minute,end):
                runtime.due(minute)
                for row in due_rows:runtime.produce(row,minute)
                runtime.prune()
                for row in due_rows:runtime.recruit(row,minute,cache)
                runtime.finalize();db.flush();runtime.processed_rounds+=1
                # Sexual partner results are tied to a bank snapshot. Physical
                # eligibility remains cached, but old bank snapshots are released.
                for key in list(cache):
                    if key[0] in ('S1_mate','S1_cohort'):cache.pop(key,None)
            runtime.due(end);p.last_minute=end;p.state_checksum=checksum([p.signature,end]);runtime.close();db.flush()
            db.info[('GA2_last_stats',cid)]={'opportunity_instants':runtime.processed_rounds,'compact_sites_checked':len(runtime.site_cache),
                                          'bodies_materialized_by_ecology':0,'E1_evaluations':runtime.v.environment.classifier.misses,
                                          'cohort_rebuilds':runtime.cohort_builds,'compact_records_validated':len(runtime.compact_cache)}
        finally:
            event.remove(db,'before_flush',runtime.finalize)
            if db.is_active:runtime.close()
            db.info.pop(('L2_batch',cid),None);db.info.pop(('L2_advancing',cid),None);db.info.pop(('L2_entities',cid),None)


def population_view(db,cid,c,pop,v):
    native=db.get(l2.Population,(cid,pop['population_id']),populate_existing=True)
    slots=native.data['slots'] if native else {};minute=life.now(db,cid)
    if native and checksum(native.data)!=native.data_checksum:raise ValueError('GA2 occupancy corrupted')
    founders=0 if native and native.data.get('cleared_minute') is not None else pop['founder_count']-len(slots)
    children=[];stages={'germinating':0,'young':0,'adult':founders};loss=0;mature=[]
    for slot,entry in sorted(slots.items()):
        if not entry.get('occupant'):continue
        if not entry.get('ga2_child'):raise ValueError('GA2 missing compact phenotype')
        rec=checked_record(entry);state=stage_record(rec,minute);stages[state['maturity']]+=1
        children.append({'id':rec['individual_id'],**state})
        loss+=Q-state['height_cm']*Q//max(1,rec['height_cm'])
        if rec['mature_minute']<=minute:mature.append(rec['mature_minute'])
    count=founders+len(children)
    return {'living_count':count,'surviving_founders':founders,'stages':stages,'children':children,
            'cover_fraction_ppm':max(0,(count*Q-loss)//pop['founder_count']),
            'first_maturity_minute':min(mature) if mature else None,
            'vacant_slots':pop['founder_count']-count,'reserved_slots':sum(bool(e.get('reservation')) for e in slots.values())}


def query_population_ga2(db,cid,community_id,sid):
    v=service.context(db,cid);p=l2.header(db,cid,v)
    l2.advance(db,cid,v);c=db.get(l2.Community,(cid,community_id));service._physical_current(db,cid,c)
    row=l2.watch(db,cid,c,sid,v,p);l2._check(row)
    pop=next(x for x in c.baseline['populations'] if x['species_id']==sid)
    view=population_view(db,cid,c,pop,v)
    return {'renewal_version':2,'renewal_policy':'adventure_renewal_ga2','population_id':row.population_id,
            'capacity':row.data['capacity'],**view,'profile':row.data['profile'],
            'bank_packets':sum(b['remaining'] for b in row.data['bank'] if b['expires']>life.now(db,cid)),
            'ledger':deepcopy(row.data['ledger']),'reproductive_budget':deepcopy(row.data.get('ga2_budget',{})),
            'timings':deepcopy(row.data.get('ga2_marks',{}))}


def materialize_child(db,cid,entry,v):
    """Hydrate one encountered occupant; its identity, position and birth stay exact."""
    record=checked_record(entry);old=db.get(l2.Individual,(cid,record['individual_id']),populate_existing=True)
    if old:return old
    p=l2.header(db,cid,v);lp=life.header(db,cid,v)
    if p.signature!=record['renewal_signature'] or lp.signature!=record['life_signature']:
        raise ValueError('GA2 child authority mismatch')
    c=db.get(l2.Community,(cid,record['community_id']))
    b=service._individual_baseline(v,c,record['species_id'],record['slot'])
    b=resources.founding_baseline(db,cid,v,b,None)
    b.update(individual_id=record['individual_id'],parent_id=record['parent_id'],birth_event_id=record['birth_event_id'],
             origin='GA2_ecological_propagule',renewal_signature=p.signature)
    if b['point']!=record['point'] or b['height_cm']!=record['height_cm']:raise ValueError('GA2 phenotype changed on encounter')
    s=resources.initial_state(b,{'alive':True,'part_stock':{k:0 for k in b['initial_part_stock']},'revision':0})
    child=l2.Individual(campaign_id=cid,individual_id=b['individual_id'],community_id=b['community_id'],
                        baseline=b,baseline_checksum=checksum(b),state=s,state_checksum=checksum(s))
    life._attach(child,lp,v);s=deepcopy(child.state);l=s['life']
    if l['profile']!=record['profile'] or l['growth_rates_ppm']!=record['growth_rates_ppm']:raise ValueError('GA2 growth phenotype mismatch')
    mass=record['escrow_mass_mg']
    l.update(birth_minute=record['birth_minute'],last_minute=record['birth_minute'],height_cm=1,maturity='germinating',
             base_mass_mg=mass,mature_tissues_initialized=False)
    s['tissue_remaining_mg']={k:0 for k in b['resource_profile']['pools_mg']}
    carried=min(mass,b['resource_profile']['pools_mg']['subterranean']);s['tissue_remaining_mg']['subterranean']=carried
    s['discarded_mass_mg']=mass-carried;l['growth_mass_mg']=dict(s['tissue_remaining_mg'])
    life._store(child,life.project(b,s,life.now(db,cid),v.catalog.species[b['species_id']]))
    db.add(child);db.flush();return child
