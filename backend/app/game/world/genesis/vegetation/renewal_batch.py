"""Batched executor for the unchanged L2 ecological rules.

The reference executor remains available for differential proofs. Mutable banks
and occupancy are staged under one SQLite writer fence; checksums are finalized
before every ORM flush. No cache or structural sharing escapes that transaction.
"""
from copy import deepcopy
from collections import OrderedDict
from sqlalchemy import event
from . import renewal as l2,lifecycle as life,service,resources
from ..terrain.field import checksum
from ..sphere_topology import SurfacePoint
from ..geology.regional.experiment import window_point


class Bank(dict):
    def __deepcopy__(self,memo):
        d=Bank(self);d['used']=dict(self['used']);return d


class State(dict):
    def __deepcopy__(self,memo):
        d=State(self)
        if 'bank' in self:
            d['bank']=[deepcopy(b,memo) for b in self['bank']];d['ledger']=dict(self['ledger'])
        else:d['slots']=dict(self['slots'])
        return d


def working(d,native=False):
    result=State(d)
    if not native:result['bank']=[Bank(b) for b in d['bank']]
    return result


def plain(d):
    result=dict(d)
    if 'bank' in result:result['bank']=[dict(b) for b in result['bank']]
    return result


class Runtime:
    def __init__(self,db,cid,v,p):
        from .renewal_readview import read_view
        self.db,self.cid,self.v,self.p=db,cid,read_view(v),p;self.dirty={};self.tokens={};self.mature={}
        self.geometry=OrderedDict();self.cohorts={}
        self.natives={r.population_id:r for r in db.query(l2.Population).filter_by(campaign_id=cid)}
        for row in self.natives.values():
            if checksum(row.data)!=row.data_checksum:raise ValueError('Corrupt L2 native occupancy')
        self.rows=list(db.query(l2.Renewing).filter_by(campaign_id=cid).order_by(l2.Renewing.population_id))
        for row in self.rows:l2._check(row)
        self.ids={r.population_id for r in self.rows}
        self.original={id(r):(r,r.data_checksum) for r in [*self.rows,*self.natives.values()]}
        for row in self.rows:row.data=working(row.data)
        for row in self.natives.values():row.data=working(row.data,True)

    def staged(self,row):
        return self.tokens.get(id(row)) is row.data

    def stage(self,row,data,native=False):
        if not native:l2.validate(data)
        data=working(data,native)
        row.data=data;self.dirty[id(row)]=row;self.tokens[id(row)]=data

    def native(self,popid):
        row=self.natives.get(popid)
        if row is None:raise ValueError('Missing L2 native occupancy')
        return row

    def finalize(self,*args):
        for row in self.dirty.values():row.data_checksum=checksum(row.data)
        self.dirty.clear()

    def adult(self,child,minute):
        s=child.state;l=s['life']
        if not s['alive']:return False
        if l['birth_minute'] is None:return l['maturity']=='adult'
        if child.individual_id not in self.mature:
            from .life_math import maturity_minute
            self.mature[child.individual_id]=maturity_minute(l)
        at=self.mature[child.individual_id];return at is not None and minute>=at

    def packet(self,target,point,minute,rows,cache):
        candidates=[]
        for source in rows:
            if source.species_id!=target.species_id:continue
            d=source.data
            if not any(b['remaining'] and b['expires']>minute for b in d['bank']):continue
            c=l2._entity(self.db,self.cid,l2.Community,source.community_id,self.v)
            pop=next(x for x in c.baseline['populations'] if x['species_id']==source.species_id)
            key=(source.population_id,tuple(point.xyz))
            geometry=self.geometry.get(key)
            if geometry is None:
                geometry=[]
                for slot in l2._near_slots(c,pop,point):
                    q=l2._slot_point(c,pop,slot)
                    identifier='vgi:'+checksum([pop['population_id'],slot])[:32]
                    distance=l2.distance_m(self.v.environment.regional.terrain.plan.source.config,point,q)
                    geometry.append((slot,identifier,list(q.xyz),distance))
                self.geometry[key]=geometry
                while len(self.geometry)>4096:self.geometry.popitem(last=False)
            else:self.geometry.move_to_end(key)
            for index,bank in enumerate(d['bank']):
                if not bank['remaining'] or bank['expires']<=minute:continue
                if bank['id'] not in self.cohorts:
                    cohort=bank['cohort'];self.cohorts[bank['id']]=(cohort['all_founders_dead'],set(cohort['excluded_founders']),{x['slot']:x for x in cohort['mature_children']})
                cleared,excluded,kids=self.cohorts[bank['id']]
                for slot,founder_id,founder_point,founder_distance in geometry:
                    child=kids.get(slot)
                    if child:
                        parent_id=child['id'];position=child['point']
                        child_key=('child',parent_id,tuple(point.xyz))
                        distance=self.geometry.get(child_key)
                        if distance is None:
                            distance=l2.distance_m(self.v.environment.regional.terrain.plan.source.config,point,SurfacePoint(*position));self.geometry[child_key]=distance
                            while len(self.geometry)>4096:self.geometry.popitem(last=False)
                    elif not cleared and slot not in excluded:parent_id=founder_id;position=founder_point;distance=founder_distance
                    else:continue
                    if bank['used'].get(parent_id,0)>=bank['per_parent'] or distance>d['profile']['dispersal_m']:continue
                    candidates.append((distance,source.population_id,index,parent_id,position,source))
        from .service import eligibility_at
        for distance,popid,index,parent_id,position,source in sorted(candidates,key=lambda x:x[:4]):
            key=(source.species_id,tuple(position))
            if key not in cache:
                q=SurfacePoint(*position);cache[key]=eligibility_at(self.db,self.cid,self.v,self.v.catalog.species[source.species_id],q)[0]=='eligible'
            if cache[key]:
                if source.data['profile'].get('sexual_policy_revision'):
                    from .sexual import compatible_mate
                    if compatible_mate(self.db,source,source.data['bank'][index],parent_id,position,self.v,cache) is None:continue
                return source,index,parent_id,position
        return None

    def prune(self):
        active={b['id'] for r in self.rows for b in r.data['bank']}
        self.cohorts={k:v for k,v in self.cohorts.items() if k in active}

    def due(self,until):
        db=self.db;events=db.query(l2.Event).filter(l2.Event.campaign_id==self.cid,l2.Event.status=='pending',l2.Event.due_minute<=until).order_by(l2.Event.population_id,l2.Event.due_minute,l2.Event.event_id).all()
        for e in events:
            if e.status!='pending':continue
            if e.population_id not in self.ids:continue
            if not e.payload.get('renewal_signature'):
                self.finalize();db.flush()
                db.info.pop(('L2_batch',self.cid),None)
                try:life.process_events(db,self.cid,e.population_id,self.v,_until=until)
                finally:db.info[('L2_batch',self.cid)]=self
                db.refresh(self.natives[e.population_id]);self.natives[e.population_id].data=working(self.natives[e.population_id].data,True)
                continue
            self.birth(e,until)
        self.finalize();db.flush()

    def birth(self,e,until):
        x=e.payload
        if checksum(x)!=e.payload_checksum or x['signature']!=life.header(self.db,self.cid,self.v).signature:raise ValueError('L1 event corrupted')
        if x['renewal_signature']!=self.p.signature:raise ValueError('L2 event authority mismatch')
        if x.get('sexual_authorization'):
            from .sexual import validate_profile
            validate_profile(self.db,self.cid,{'sexual_policy_signature':x['sexual_authorization']['policy_signature']})
        native=self.native(e.population_id);data=deepcopy(native.data)
        key=str(x['slot']);slot=dict(data['slots'][key]);data['slots'][key]=slot
        if slot['reservation']!=e.event_id or slot['occupant']:raise ValueError('L1 reservation mismatch')
        b=deepcopy(x['target_baseline']);b.update(individual_id=x['child_id'],origin='L2_ecological_propagule',parent_id=x['parent_id'],birth_event_id=e.event_id,renewal_signature=x['renewal_signature'])
        c=l2._entity(self.db,self.cid,l2.Community,b['community_id'],self.v)
        pop=next(p for p in c.baseline['populations'] if p['species_id']==b['species_id'])
        if not 0<=b['slot']<pop['founder_count']:raise ValueError('Invalid canonical founder slot')
        canonical=l2._slot_point(c,pop,b['slot']);salt=int(checksum([e.event_id,'microsite'])[:8],16)
        point=window_point(canonical,1+salt%5,1+(salt//5)%5,self.v.radius*100);b['point']=list(point.xyz)
        from .service import eligibility_at
        sp=self.v.catalog.species[b['species_id']]
        if eligibility_at(self.db,self.cid,self.v,sp,point)[0]!='eligible':
            e.status='failed_habitat';slot['reservation']=None;self.stage(native,data,True);return
        s=resources.initial_state(b,{'alive':True,'part_stock':{k:0 for k in b['initial_part_stock']},'revision':0})
        child=l2.Individual(campaign_id=self.cid,individual_id=b['individual_id'],community_id=b['community_id'],baseline=b,baseline_checksum=checksum(b),state=s,state_checksum=checksum(s))
        life._attach(child,life.header(self.db,self.cid,self.v),self.v);s=deepcopy(child.state);l=s['life']
        l.update(birth_minute=e.due_minute,last_minute=e.due_minute,height_cm=1,maturity='germinating',base_mass_mg=x['escrow_mass_mg'],mature_tissues_initialized=False)
        s['tissue_remaining_mg']={k:0 for k in b['resource_profile']['pools_mg']}
        carried=min(b['resource_profile']['pools_mg']['subterranean'],x['escrow_mass_mg'])
        s['tissue_remaining_mg']['subterranean']=carried;s['discarded_mass_mg']=x['escrow_mass_mg']-carried;l['growth_mass_mg']=dict(s['tissue_remaining_mg'])
        life._store(child,life.project(b,s,until,sp));self.db.add(child)
        slot.update(occupant=child.individual_id,reservation=None);e.status='established';self.stage(native,data,True)

    def close(self):
        self.finalize()
        for row in [*self.rows,*self.natives.values()]:row.data=plain(row.data)


def advance_batch(db,cid,v,p):
    end=life.now(db,cid)
    if end<p.last_minute:raise ValueError('L2 ecological time cannot move backwards')
    if end==p.last_minute:return
    service._fence(db,cid)
    with db.begin_nested(),db.no_autoflush:
        p=l2.header(db,cid,v);runtime=Runtime(db,cid,v,p);v=runtime.v
        db.info[('L2_advancing',cid)]=True;db.info[('L2_entities',cid)]={};db.info[('L2_batch',cid)]=runtime
        event.listen(db,'before_flush',runtime.finalize)
        try:
            cache={}
            for minute in l2.rounds(p.last_minute,end):
                runtime.due(minute)
                for row in runtime.rows:l2._produce(db,cid,row,v,p,minute)
                runtime.prune()
                for row in runtime.rows:l2._recruit(db,cid,row,runtime.rows,v,p,minute,cache)
                runtime.finalize();db.flush()
            runtime.due(end);p.last_minute=end;p.state_checksum=checksum([p.signature,end])
            runtime.close();db.flush()
            memo=v.environment.classifier
            db.info[('L2_last_batch_stats',cid)]={'E1_original_evaluations':memo.misses,'E1_memo_hits':memo.hits,'E1_memo_entries':len(memo.cache),'E1_authority_modified':False}
        finally:
            event.remove(db,'before_flush',runtime.finalize)
            if db.is_active:runtime.close()
            db.info.pop(('L2_batch',cid),None);db.info.pop(('L2_advancing',cid),None);db.info.pop(('L2_entities',cid),None)


def query_population_batch(db,cid,community_id,sid):
    v=service.context(db,cid)
    if l2.header(db,cid,v) is None:raise ValueError('Explicit L2 required')
    l2.advance(db,cid,v);c=db.get(l2.Community,(cid,community_id));row=l2.watch(db,cid,c,sid,v);l2._check(row)
    service._physical_current(db,cid,c)
    pop=next(p for p in c.baseline['populations'] if p['species_id']==sid)
    # Keep all participants strongly referenced and validate the source once, rather
    # than reloading the authority and each child twice through the ORM weak map.
    all_rows=list(db.query(l2.Individual).filter_by(campaign_id=cid,community_id=community_id));by_id={}
    minute=life.now(db,cid);sp=v.catalog.species[sid]
    for child in all_rows:
        if child.baseline['species_id']!=sid:continue
        service._validate_individual(child)
        life._store(child,life.project(child.baseline,child.state,minute,sp));by_id[child.individual_id]=child
    native=db.get(l2.Population,(cid,pop['population_id']),populate_existing=True)
    if native is None:count=pop['founder_count'];fraction=life.Q
    else:
        if checksum(native.data)!=native.data_checksum:raise ValueError('L1 population corrupted')
        vacant=0;loss=0
        for slot in native.data['slots'].values():
            if not slot.get('occupant'):vacant+=1
            else:
                child=by_id[slot['occupant']]
                loss+=life.Q-child.state['life']['height_cm']*life.Q//max(1,child.baseline['height_cm'])
        count=(sum(bool(s.get('occupant')) for s in native.data['slots'].values()) if native.data.get('cleared_minute') is not None else pop['founder_count']-vacant)
        fraction=max(0,(count*life.Q-loss)//pop['founder_count'])
    children=[x for x in all_rows if x.baseline['species_id']==sid and x.baseline.get('birth_event_id') and x.state['alive']]
    stages={'germinating':0,'young':0,'adult':0}
    for child in children:stages[child.state['life']['maturity']]+=1
    stages['adult']+=count-len(children)
    return {'renewal_version':2,'population_id':row.population_id,'capacity':row.data['capacity'],'living_count':count,'stages':stages,
        'cover_fraction_ppm':fraction,'bank_packets':sum(b['remaining'] for b in row.data['bank'] if b['expires']>minute),
        'ledger':deepcopy(row.data['ledger']),'profile':row.data['profile'],'children':[{'id':x.individual_id,'birth_minute':x.state['life']['birth_minute'],
            'height_cm':x.state['life']['height_cm'],'maturity':x.state['life']['maturity']} for x in children]}
