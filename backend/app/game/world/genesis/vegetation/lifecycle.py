"""L1 opt-in, lazy biological time. Finite escrowed dispersal; no visit rolls.

The caller owns the transaction. All mutations share Vg2's SQLite writer fence.
Environmental rates are frozen seasonal suitability, not a water-stock simulation.
"""
from copy import deepcopy
from sqlalchemy import update
from app.db.models.world_vegetation_lifecycle import GenesisVegetationLife as Plan,GenesisLivingPopulation as Population,GenesisVegetationLifeEvent as Event
from app.db.models.world_vegetation import GenesisPlantIndividual as Individual,GenesisVegetationCommunity as Community
from app.game.time.clock import get_world_time
from ..terrain.field import checksum
from ..sphere_topology import SurfacePoint
from ..sphere_metric import distance_m
from .life_math import LifeConfigL1,life_profile,work,time_for_work,windows,DAY,YEAR,Q,PARTIAL,GROWTH,RARITY
from . import resources
from .growth_gameplay import LifeConfigGA1,parse_config,attach_profile
from .life_math import growth_clock


def now(db,cid):return get_world_time(db,cid).total_minutes()


def header(db,cid,v):
    p=db.get(Plan,cid,populate_existing=True)
    if p is None:return None
    d=p.descriptor;r=resources.header(db,cid,v)
    if (checksum(d)!=p.descriptor_checksum or checksum(d)[:24]!=p.signature or r is None or
        d['resource_signature']!=r.signature or d['vegetation_signature']!=v.signature or
        d['rules']!=rules()):raise ValueError('L1 authority changed or corrupted')
    cfg=parse_config(d['config'])
    if isinstance(cfg,LifeConfigGA1):
        from .growth_gameplay import rules as growth_rules
        if d.get('growth_policy_rules')!=growth_rules():raise ValueError('GA1 growth authority changed or corrupted')
    return p


def rules():
    return {'version':1,'rarity':{k:list(v) for k,v in RARITY.items()},'growth':{k:list(v) for k,v in GROWTH.items()},
        'partial_tissue':sorted(PARTIAL),'calendar':'360_day_seasonal_integral_v1',
        'capacity':'unchanged_finite_Vg2_founder_slots','propagation':'finite_raw_abiotic_escrow_v1',
        'growth_allometry':'height_linear_biomass_squared_matching_R1',
        'environment':'frozen_C3_W1_suitability_not_daily_water_budget'}


def initialize_life(db,cid,config=None,*,experimental=False):
    from . import service
    if experimental is not True:raise ValueError('Explicit experimental L1 activation required')
    v=service.context(db,cid);r=resources.header(db,cid,v)
    if r is None:raise ValueError('L1 requires explicit R1')
    cfg=parse_config((config or LifeConfigL1()).model_dump(mode='json'));old=header(db,cid,v)
    ids=set(v.catalog.species)|{p['id'] for s in v.catalog.species.values() for p in s.parts()}
    if set(cfg.overrides)-ids:raise ValueError('Unknown lifecycle override')
    if isinstance(cfg,LifeConfigGA1):
        if any(sid not in v.catalog.species or v.catalog.species[sid].kind!='arvore' for sid in cfg.tree_pacing):
            raise ValueError('GA1 tree pacing requires real tree species')
    if old:
        if old.descriptor['config']!=cfg.model_dump(mode='json'):raise ValueError('Cannot reconfigure L1')
        return old
    service._fence(db,cid)
    d={'kind':'vegetation_life_l1','version':1,'config':cfg.model_dump(mode='json'),'rules':rules(),
        'resource_signature':r.signature,'vegetation_signature':v.signature,'activation_minute':now(db,cid),
        'legacy_policy':'explicit_cutover_preserves_ids_baselines_and_existing_deaths'}
    if isinstance(cfg,LifeConfigGA1):
        from .growth_gameplay import rules as growth_rules
        d.update(kind='vegetation_life_l1_ga1',growth_policy_rules=growth_rules())
    p=Plan(campaign_id=cid,signature=checksum(d)[:24],descriptor=d,descriptor_checksum=checksum(d),write_epoch=0)
    db.add(p);db.flush()
    # Only already materialized states are cut over; never enumerate virtual plants.
    established=list(db.query(Individual).filter_by(campaign_id=cid).order_by(Individual.individual_id))
    for row in established:
        if 'resource_signature' in row.baseline:_attach(row,p,v)
    for row in established:
        if 'life' in row.state and not row.state['alive']:record_death(db,cid,row,v,p)
    return p


def _store(row,state):
    row.state=state;row.state_checksum=checksum(state)


def _attach(row,p,v):
    if 'life' in row.state:
        if row.state['life']['signature']!=p.signature:raise ValueError('L1 individual authority mismatch')
        return
    if 'resource_signature' not in row.baseline:return
    s=deepcopy(row.state);sp=v.catalog.species[row.baseline['species_id']]
    environmental_rates=rates(v,row.baseline,sp)
    profile,growth_rates=attach_profile(sp,parse_config(p.descriptor['config']),row.baseline,environmental_rates)
    s['life']={'version':1,'signature':p.signature,'last_minute':p.descriptor['activation_minute'],
        'birth_minute':None,'profile':profile,
        'rates':environmental_rates,'fraction':{k:0 for k in s['part_stock']},
        'assimilated_mass_mg':0,'dispersed_mass_mg':0,'base_mass_mg':sum(row.baseline['resource_profile']['pools_mg'].values()),
        'height_cm':row.baseline['height_cm'],'maturity':'adult','growth_mass_mg':dict(row.baseline['resource_profile']['pools_mg']),
        'death_recorded':False,'mature_tissues_initialized':True}
    if growth_rates is not None:s['life']['growth_rates_ppm']=growth_rates
    _store(row,s)


def rates(v,b,sp):
    point=SurfacePoint(*b['point']);e=v.environment.sample(point);w=v.water_facts(point)
    from .field import eligibility
    if b.get('microenvironment_context') is not None:
        from .service import apply_local_environment
        e=apply_local_environment(e,b['microenvironment_context'])
    if eligibility(sp,e,w)[0]!='eligible':return [0]*4
    out=[]
    # Water limitation reduces rate, never fabricates a measured local water stock.
    for i,s in enumerate(e['physical_inputs']['C3_seasons']):
        t=s['temperature_centi_c'];et=v.water.solution.periods[i]['fluxes']['evapotranspiration'][w['node']]
        out.append(0 if et<=0 or t<=0 else Q if t>=500 else max(1,t*Q//500))
    return out


def _phase(p):return None if p['maturity_required']=='adult' else p['maturity_required']


def project(b,state,end,sp):
    """Pure semigroup projection; integer remainders preserve fragmented visits."""
    s=deepcopy(state);l=s['life'];start=l['last_minute']
    if end<start:raise ValueError('Ecological time cannot move backwards')
    if end==start:return s
    profile=l['profile'];r=l['rates'];growth_seasons=profile['growth_seasons'];begin=start
    if s['alive'] and l['birth_minute'] is not None:
        growth_rates,growth_seasons=growth_clock(l)
        birth=l['birth_minute'];age=work(birth,end,growth_rates,growth_seasons)
        mature=profile['mature_active_days']*DAY*Q;germ=profile['germination_active_days']*DAY*Q
        l['maturity']='germinating' if age<germ else 'young' if age<mature else 'adult'
        l['height_cm']=max(1,b['height_cm']*min(age,mature)//mature)
        # Structural assimilation has an explicit ledger and a finite adult cap.
        for pool,cap in b['resource_profile']['pools_mg'].items():
            target=cap*min(age,mature)**2//mature**2
            delta=max(0,target-l['growth_mass_mg'][pool]);l['growth_mass_mg'][pool]=max(target,l['growth_mass_mg'][pool])
            room=cap-s['tissue_remaining_mg'][pool];delta=min(room,delta)
            s['tissue_remaining_mg'][pool]+=delta;l['assimilated_mass_mg']+=delta
        adult_at=time_for_work(birth,mature,growth_rates,growth_seasons)
        begin=max(start,adult_at) if adult_at is not None else end
    if s['alive'] and l['maturity']=='adult':
        if not l['mature_tissues_initialized']:
            for pid,p in b['resource_profile']['parts'].items():
                if p['state']=='usable' and p['part'] not in PARTIAL:s['part_stock'][pid]=p['max_units']
            l['mature_tissues_initialized']=True
        raw={p['id']:p for p in sp.parts()}
        for pid,p in b['resource_profile']['parts'].items():
            if p['state']!='usable' or p['part'] not in PARTIAL:continue
            cap=p['max_units'];current=s['part_stock'][pid]
            if current>=cap:l['fraction'][pid]=0;continue
            elapsed=work(begin,end,r,raw[pid]['disponibilidade']['estacoes'],_phase(p))
            denominator=profile['recovery_days'][pid]*DAY*Q
            units,remainder=divmod(l['fraction'][pid]+elapsed*cap,denominator)
            added=min(cap-current,units);s['part_stock'][pid]+=added
            l['fraction'][pid]=0 if current+added==cap else remainder
            mass=added*p['unit_mass_mg'];pool=p['pool']
            credit=min(mass,b['resource_profile']['pools_mg'][pool]-s['tissue_remaining_mg'][pool])
            s['tissue_remaining_mg'][pool]+=credit;l['assimilated_mass_mg']+=credit
    l['last_minute']=end
    validate(b,s)
    return s


def validate(b,s):
    l=s['life'];p=b['resource_profile'];values=[*s['tissue_remaining_mg'].values(),s['exported_mass_mg'],s['discarded_mass_mg'],l['dispersed_mass_mg']]
    if (any(type(x)is not int or x<0 for x in values) or sum(values)!=l['base_mass_mg']+l['assimilated_mass_mg']):
        raise ValueError('L1 mass conservation mismatch')
    if l['maturity'] not in ('germinating','young','adult'):raise ValueError('Invalid L1 maturity')
    for pid,n in s['part_stock'].items():
        if type(n)is not int or not 0<=n<=p['parts'][pid]['max_units']:raise ValueError('L1 stock outside R1 cap')
        if (not s['alive'] or l['maturity']!='adult') and n:raise ValueError('Dead/young plant has mature stock')
    for pool,left in s['tissue_remaining_mg'].items():
        if left>p['pools_mg'][pool] or sum(x['unit_mass_mg']*s['part_stock'][pid] for pid,x in p['parts'].items() if x['pool']==pool)>left:
            raise ValueError('L1 shared tissue allocation exceeded')


def sync(db,cid,row,v=None,*,events=True):
    from . import service
    v=v or service.context(db,cid);p=header(db,cid,v)
    if p is None:
        if 'life' in row.state:raise ValueError('Missing L1 authority')
        return row
    if 'resource_signature' not in row.baseline:return row
    from . import renewal
    renewal.advance(db,cid,v)
    if row.baseline.get('renewal_signature'):
        from ..environment.service import materialize_environment_point
        materialize_environment_point(db,cid,SurfacePoint(*row.baseline['point']),_sampler=v.environment)
    service.query_environment(db,cid,SurfacePoint(*row.baseline['point']),_sampler=v.environment)
    service._fence(db,cid)
    db.refresh(row)
    if events:process_events(db,cid,row.baseline['population_id'],v,p)
    service._validate_individual(row);_attach(row,p,v)
    renewal.before_sync(db,cid,row,v)
    pop=db.get(Population,(cid,row.baseline['population_id']),populate_existing=True)
    if pop is not None:
        if checksum(pop.data)!=pop.data_checksum:raise ValueError('L1 population corrupted')
        if pop.data.get('cleared_minute') is not None and row.baseline.get('birth_event_id') is None and row.state['alive']:
            state=deepcopy(row.state);kill_state(state);_store(row,state)
    if row.state['life']['last_minute']!=now(db,cid):
        _store(row,project(row.baseline,row.state,now(db,cid),v.catalog.species[row.baseline['species_id']]))
    if not row.state['alive']:record_death(db,cid,row,v,p)
    return row


def harvest_state(b,state,pid,quantity,minute):
    p=b['resource_profile']['parts'][pid];s=deepcopy(state)
    if s['life']['maturity']!='adult':raise ValueError('Young plant cannot yield mature resources')
    if quantity>p['per_action_max'] or quantity>s['part_stock'][pid]:raise ValueError('Insufficient finite stock or per-action cap')
    mass=quantity*p['unit_mass_mg']
    if mass>s['tissue_remaining_mg'][p['pool']]:raise ValueError('Insufficient tissue')
    s['part_stock'][pid]-=quantity;s['tissue_remaining_mg'][p['pool']]-=mass;s['exported_mass_mg']+=mass
    # Partial collection does not discard growth already accumulated below the cap.
    s['revision']+=1;s['last_harvest_world_minute']=minute;s['last_removed_part']=pid
    if p['part'] not in PARTIAL:kill_state(s)
    validate(b,s);return s,mass


def kill_state(s):
    s['alive']=False;s['discarded_mass_mg']+=sum(s['tissue_remaining_mg'].values())
    s['tissue_remaining_mg']={k:0 for k in s['tissue_remaining_mg']};s['part_stock']={k:0 for k in s['part_stock']}


def population(db,cid,community,spid):
    pop=next(p for p in community.baseline['populations'] if p['species_id']==spid)
    db.flush()
    row=db.get(Population,(cid,pop['population_id']),populate_existing=True)
    if row is None:
        d={'capacity':pop['founder_count'],'slots':{}}
        row=Population(campaign_id=cid,population_id=pop['population_id'],community_id=community.community_id,species_id=spid,data=d,data_checksum=checksum(d))
        db.add(row);db.flush()
    if checksum(row.data)!=row.data_checksum or row.data['capacity']!=pop['founder_count']:raise ValueError('L1 population corrupted')
    return row


def _popwrite(row,d):
    from sqlalchemy.orm import object_session
    session=object_session(row);runtime=session.info.get(('L2_batch',row.campaign_id)) if session else None
    if runtime is not None:return runtime.stage(row,d,native=True)
    row.data=d;row.data_checksum=checksum(d)


def record_death(db,cid,row,v,p=None):
    l=row.state['life']
    if l['death_recorded']:return
    p=p or header(db,cid,v);c=db.get(Community,(cid,row.community_id));pop=population(db,cid,c,row.baseline['species_id'])
    d=deepcopy(pop.data);slot=str(row.baseline['slot']);previous=d['slots'].get(slot,{})
    if previous.get('ga2_child'):
        from .renewal_gameplay import retire_compact
        retire_compact(d,previous,now(db,cid))
    if previous.get('occupant') not in (None,row.individual_id):raise ValueError('L1 occupied slot identity mismatch')
    d['slots'][slot]={'dead_founder':True,'occupant':None,'reservation':None};_popwrite(pop,d)
    s=deepcopy(row.state);s['life']['death_recorded']=True;s['life']['death_minute']=now(db,cid);_store(row,s)
    from .renewal import on_death
    if on_death(db,cid,row,v):return
    cfg=parse_config(p.descriptor['config'])
    if cfg.automatic_colonization and pop.data.get('cleared_minute') is None:
        # Fixed inverse-address neighbours across patch/face seams. No visit rolls.
        from .actions import _nearby_slots
        from . import service
        from ..geology.regional.experiment import window_point
        center=SurfacePoint(*row.baseline['point']);radius=cfg.dispersal_m
        queries={v.address(q)[1]:q for q in (window_point(center,x,y,v.radius) for x in (-radius,0,radius) for y in (-radius,0,radius))}
        communities={c.community_id:c};candidates=[]
        for identifier,q in sorted(queries.items()):
            if identifier not in communities:
                if row.baseline['species_id'] not in {x['species_id'] for x in service.sample_initial_community(db,cid,v,q)['populations']}:continue
                communities[identifier]=service.materialize_community(db,cid,q)
            for distance,sid,slot,point in _nearby_slots(v,communities[identifier],center,radius_m=radius):
                if sid==row.baseline['species_id']:candidates.append((distance,identifier,slot,point))
        for distance,identifier,slot,point in sorted(candidates,key=lambda x:x[:3]):
            if identifier==row.community_id and slot==row.baseline['slot']:continue
            try:parent=service.materialize_individual(db,cid,point,row.baseline['species_id'],slot,_sampler=v,_community=communities[identifier])
            except ValueError as exc:
                if 'microsite unsupported' in str(exc):continue
                raise
            parent=current_occupant(db,cid,parent,v)
            if parent.state['alive'] and parent.baseline['species_id']==row.baseline['species_id']:
                try:disperse(db,cid,parent.individual_id,row.individual_id,'death:'+row.individual_id,_v=v)
                except ValueError as exc:
                    if not str(exc).startswith('Propagation unavailable:'):raise
                else:break


def phase_available(b,state,pid,minute,sp):
    if 'life' not in state:return True
    if state['life']['maturity']!='adult':return False
    p=b['resource_profile']['parts'][pid]
    return any(a<=minute%YEAR<z for a,z,r in windows([Q]*4,phase=_phase(p)))


def disperse(db,cid,parent_id,target_dead_id,event_key,*,_v=None):
    """Explicit ecological event, finite parent escrow. Target is an existing tombstone.

    This trusted API accepts no habitat claims and creates no inventory items.
    No player endpoint is exposed; caller's transaction/checkpoint includes all rows.
    """
    from . import service
    if not isinstance(event_key,str) or not 1<=len(event_key)<=160:raise ValueError('Bounded ecological event key required')
    v=_v or service.context(db,cid);p=header(db,cid,v)
    if p is None:raise ValueError('Explicit L1 required')
    eid='vle:'+checksum([p.signature,event_key])[:32]
    old=db.get(Event,(cid,eid))
    if old:
        if checksum(old.payload)!=old.payload_checksum or old.payload['parent_id']!=parent_id or old.payload['target_dead_id']!=target_dead_id:
            raise ValueError('Ecological key collision or corruption')
        return old
    service._fence(db,cid)
    with db.begin_nested():
        old=db.get(Event,(cid,eid),populate_existing=True)
        if old:
            if checksum(old.payload)!=old.payload_checksum or old.payload['parent_id']!=parent_id or old.payload['target_dead_id']!=target_dead_id:raise ValueError('Ecological key collision or corruption')
            return old
        parent=db.get(Individual,(cid,parent_id),populate_existing=True);target=db.get(Individual,(cid,target_dead_id),populate_existing=True)
        if parent is None or target is None:raise ValueError('Propagation unavailable: actual parent and tombstone required')
        sync(db,cid,parent,v,events=False);sync(db,cid,target,v,events=False)
        b=parent.baseline;sp=v.catalog.species[b['species_id']];cfg=parse_config(p.descriptor['config'])
        if (not parent.state['alive'] or target.state['alive'] or b['species_id']!=target.baseline['species_id'] or
            parent.state['life']['maturity']!='adult' or sp.magic=='excepcional'):
            raise ValueError('Propagation unavailable: no living mature compatible parent')
        if distance_m(v.environment.regional.terrain.plan.source.config,SurfacePoint(*b['point']),SurfacePoint(*target.baseline['point']))>cfg.dispersal_m:
            raise ValueError('Propagation unavailable: beyond abiotic dispersal range')
        c=db.get(Community,(cid,target.community_id));pop=population(db,cid,c,sp.id);slot=str(target.baseline['slot'])
        d=deepcopy(pop.data);vacancy=d['slots'].get(slot)
        if not vacancy or vacancy.get('occupant') or vacancy.get('reservation'):raise ValueError('Propagation unavailable: no vacant capacity')
        from .field import eligibility
        point=SurfacePoint(*target.baseline['point'])
        service.query_environment(db,cid,point)
        service.query_environment(db,cid,SurfacePoint(*parent.baseline['point']))
        if service.eligibility_at(db,cid,v,sp,point)[0]!='eligible':raise ValueError('Propagation unavailable: habitat unsupported')
        # Canonical dispersal organs; clonal branches/fragments require catalog strategy.
        strategy=str(parent.state['life']['profile']['propagation_strategy']).lower()
        labels={'sementes','frutos','propagulos','esporos'}
        if any(s in strategy for s in ('fragment','vegetativ','clonal','rizoma','estol')):labels|={'ramos','fragmentos','fragmento_talo','filamentos','fragmento_lamina'}
        raw={part['id']:part for part in sp.parts()};minute=now(db,cid)
        choices=[(pid,x) for pid,x in b['resource_profile']['parts'].items() if x['part'] in labels and x['state']=='usable'
            and parent.state['part_stock'][pid]>0 and phase_available(b,parent.state,pid,minute,sp)
            and work(minute,minute+1,parent.state['life']['rates'],raw[pid]['disponibilidade']['estacoes'],_phase(x))>0]
        if not choices:raise ValueError('Propagation unavailable: no finite eligible propagule in current phenology')
        pid,x=sorted(choices)[0];s=deepcopy(parent.state);mass=x['unit_mass_mg']
        s['part_stock'][pid]-=1;s['tissue_remaining_mg'][x['pool']]-=mass;s['life']['dispersed_mass_mg']+=mass
        s['revision']+=1;validate(b,s);_store(parent,s)
        due=time_for_work(now(db,cid),cfg.establishment_days*DAY*Q,rates(v,target.baseline,sp),s['life']['profile']['growth_seasons'])
        if due is None:raise ValueError('Propagation unavailable: no establishment window')
        payload={'version':1,'parent_id':parent_id,'target_dead_id':target_dead_id,'species_id':sp.id,
            'part_id':pid,'escrow_mass_mg':mass,'created_minute':now(db,cid),'target_baseline':deepcopy(target.baseline),
            'child_id':'vgi:l1:'+checksum([eid,target.individual_id])[:32],'slot':target.baseline['slot'],
            'propagation':'versioned_abiotic_no_fauna_assumed','signature':p.signature}
        event=Event(campaign_id=cid,event_id=eid,population_id=pop.population_id,due_minute=due,status='pending',payload=payload,payload_checksum=checksum(payload))
        db.add(event);vacancy['reservation']=eid;_popwrite(pop,d);db.flush();return event


def process_events(db,cid,popid,v,p=None,*,_until=None):
    p=p or header(db,cid,v)
    if p is None:return
    if _until is None:
        from .renewal import advance
        advance(db,cid,v)
    until=now(db,cid) if _until is None else _until
    from . import service
    service._fence(db,cid)
    events=db.query(Event).populate_existing().filter(Event.campaign_id==cid,Event.population_id==popid,Event.status=='pending',Event.due_minute<=until).order_by(Event.due_minute,Event.event_id).all()
    for event in events:
        x=event.payload
        if checksum(x)!=event.payload_checksum or x['signature']!=p.signature:raise ValueError('L1 event corrupted')
        pop=db.get(Population,(cid,popid),populate_existing=True);d=deepcopy(pop.data)
        if checksum(d)!=pop.data_checksum:raise ValueError('L1 population corrupted')
        slot=d['slots'][str(x['slot'])]
        if slot['reservation']!=event.event_id or slot['occupant']:raise ValueError('L1 reservation mismatch')
        b=deepcopy(x['target_baseline']);b.update(individual_id=x['child_id'],origin='L1_finite_propagule',parent_id=x['parent_id'],birth_event_id=event.event_id)
        if x.get('renewal_signature'):b.update(renewal_signature=x['renewal_signature'],origin='L2_ecological_propagule')
        # Distinct position within the finite physical slot, no adult identity reused.
        from ..geology.regional.experiment import window_point
        from . import service
        c=db.get(Community,(cid,b['community_id']))
        canonical=service._individual_baseline(v,c,b['species_id'],b['slot'])
        salt=int(checksum([event.event_id,'microsite'])[:8],16)
        q=window_point(SurfacePoint(*canonical['point']),1+salt%5,1+(salt//5)%5,v.radius*100)
        b['point']=list(q.xyz)
        sp=v.catalog.species[b['species_id']]
        from .field import eligibility
        if service.eligibility_at(db,cid,v,sp,q)[0]!='eligible':
            event.status='failed_habitat';slot['reservation']=None;_popwrite(pop,d);continue
        from ..environment.service import materialize_environment_point
        if not x.get('renewal_signature'):materialize_environment_point(db,cid,q)
        zero={k:0 for k in b['initial_part_stock']};s=resources.initial_state(b,{'alive':True,'part_stock':zero,'revision':0})
        row=Individual(campaign_id=cid,individual_id=b['individual_id'],community_id=b['community_id'],baseline=b,baseline_checksum=checksum(b),state=s,state_checksum=checksum(s))
        _attach(row,p,v);s=deepcopy(row.state);l=s['life'];l.update(birth_minute=event.due_minute,last_minute=event.due_minute,height_cm=1,maturity='germinating',base_mass_mg=x['escrow_mass_mg'],mature_tissues_initialized=False)
        s['tissue_remaining_mg']={k:0 for k in b['resource_profile']['pools_mg']}
        # All finite seed biomass is carried in the subterranean/establishment pool.
        seed_pool='subterranean';cap=b['resource_profile']['pools_mg'][seed_pool]
        carried=min(cap,x['escrow_mass_mg']);s['tissue_remaining_mg'][seed_pool]=carried;s['discarded_mass_mg']=x['escrow_mass_mg']-carried
        l['growth_mass_mg']=dict(s['tissue_remaining_mg']);_store(row,project(b,s,until,sp))
        db.add(row);slot.update(occupant=row.individual_id,reservation=None);_popwrite(pop,d);event.status='established';db.flush()


def population_counts(db,cid,community,pop,v):
    p=header(db,cid,v)
    if p is None:return None
    process_events(db,cid,pop['population_id'],v,p)
    from .renewal import header as renewal_header
    renewal=renewal_header(db,cid,v)
    if renewal is not None and renewal.descriptor['kind']=='vegetation_renewal_ga2':
        from .renewal_gameplay import population_view
        view=population_view(db,cid,community,pop,v)
        return view['living_count'],view['cover_fraction_ppm']
    # Only persisted participants, never the millions of implicit founders.
    individuals=db.query(Individual).filter_by(campaign_id=cid,community_id=community.community_id).all()
    for row in individuals:
        if row.baseline['species_id']==pop['species_id']:
            from .renewal import header as renewal_header
            if renewal_header(db,cid,v) is None:sync(db,cid,row,v,events=False)
            else:
                from .service import _validate_individual
                _validate_individual(row)
                _store(row,project(row.baseline,row.state,now(db,cid),v.catalog.species[row.baseline['species_id']]))
    state=db.get(Population,(cid,pop['population_id']),populate_existing=True)
    if state is None:return pop['founder_count'],Q
    if checksum(state.data)!=state.data_checksum:raise ValueError('L1 population corrupted')
    vacant=0;growth_loss=0
    for slot in state.data['slots'].values():
        if not slot.get('occupant'):vacant+=1
        else:
            child=db.get(Individual,(cid,slot['occupant']))
            growth_loss+=Q-child.state['life']['height_cm']*Q//max(1,child.baseline['height_cm'])
    if state.data.get('cleared_minute') is not None:
        count=sum(bool(s.get('occupant')) for s in state.data['slots'].values())
    else:count=pop['founder_count']-vacant
    return count,max(0,(count*Q-growth_loss)//pop['founder_count'])


def current_occupant(db,cid,founder,v):
    """Discovery uses finite slot occupancy, keeping the original tombstone queryable."""
    pop=db.get(Population,(cid,founder.baseline['population_id']),populate_existing=True)
    if pop is None:return founder
    if checksum(pop.data)!=pop.data_checksum:raise ValueError('L1 population corrupted')
    entry=pop.data['slots'].get(str(founder.baseline['slot']),{})
    if not entry.get('occupant'):return founder
    child=db.get(Individual,(cid,entry['occupant']))
    if child is None and entry.get('ga2_child'):
        from .renewal_gameplay import materialize_child
        child=materialize_child(db,cid,entry,v)
    if child is None:raise ValueError('Missing L1 occupant')
    return sync(db,cid,child,v)


def clear_population(db,cid,community_id,species_id,event_key,*,reason,experimental=False):
    """Trusted finite ecological disturbance for tests/tools, never a public claim.

    Sparse extinction includes implicit founders without enumerating them. Future
    visits see tombstones; recolonization needs an external finite parent event.
    """
    from . import service
    if experimental is not True or not reason or not 1<=len(event_key)<=160:raise ValueError('Explicit bounded disturbance required')
    v=service.context(db,cid);p=header(db,cid,v)
    if p is None:raise ValueError('L1 required')
    eid='vle:'+checksum([p.signature,'clear',event_key])[:32]
    old=db.get(Event,(cid,eid))
    if old:
        if checksum(old.payload)!=old.payload_checksum or old.payload['community_id']!=community_id or old.payload['species_id']!=species_id or old.payload['reason']!=reason:
            raise ValueError('Disturbance key collision')
        return old
    service._fence(db,cid)
    with db.begin_nested():
        c=db.get(Community,(cid,community_id))
        if c is None:raise ValueError('Actual community required')
        service._validate_community(c,v);service._physical_current(db,cid,c)
        pop=population(db,cid,c,species_id);process_events(db,cid,pop.population_id,v,p)
        d=deepcopy(pop.data);d['cleared_minute']=now(db,cid)
        for entry in d['slots'].values():
            if entry.get('ga2_child'):
                from .renewal_gameplay import retire_compact
                retire_compact(d,entry,now(db,cid))
            entry.update(occupant=None,reservation=None)
        _popwrite(pop,d)
        for event in db.query(Event).filter_by(campaign_id=cid,population_id=pop.population_id,status='pending'):
            event.status='cancelled_disturbance'
        for row in db.query(Individual).filter_by(campaign_id=cid,community_id=community_id):
            if row.baseline['species_id']!=species_id:continue
            sync(db,cid,row,v,events=False)
            if 'life' not in row.state:raise ValueError('Explicit reconciliation required for legacy non-R1 individual')
            s=deepcopy(row.state)
            if s['alive']:kill_state(s)
            s['life']['death_recorded']=True;_store(row,s)
            d=deepcopy(pop.data);d['slots'][str(row.baseline['slot'])]={'dead_founder':True,'occupant':None,'reservation':None};_popwrite(pop,d)
        payload={'kind':'clear_population','version':1,'community_id':community_id,'species_id':species_id,'reason':reason,'signature':p.signature}
        from .renewal import on_clear
        on_clear(db,cid,community_id,species_id,v)
        row=Event(campaign_id=cid,event_id=eid,population_id=pop.population_id,due_minute=now(db,cid),status='disturbance_applied',payload=payload,payload_checksum=checksum(payload))
        db.add(row);db.flush();return row
