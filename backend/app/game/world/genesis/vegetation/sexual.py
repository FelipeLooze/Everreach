"""S1: explicit abstract sexual reproduction, no simulated pollinator entities.

Unspecified vectors are not specialized-agent obligations. Existing clonal/spore
routes and all L2 hashes stay intact. Only previously pending ordinary seed routes
receive the new, signed authorization, prospectively from explicit activation.
"""
import json,re,unicodedata
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from app.db.models.world_vegetation_sexual import GenesisVegetationSexualPolicy as Policy
from . import catalog
from ..terrain.field import checksum
from ..sphere_topology import SurfacePoint
from ..sphere_metric import distance_m


def normalized(value):return unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()


def specialized_requirements(obj):
    """Audit explicit reproductive obligations, not flavor or generic cautions."""
    found=[]
    def walk(value,path):
        if isinstance(value,dict):
            for k,v in value.items():walk(v,path+'.'+k)
        elif isinstance(value,list):
            for v in value:walk(v,path+'[]')
        else:
            key=normalized(path);text=normalized(str(value))
            reproductive=any(x in key for x in ('reprod','poliniz','fecund'))
            special=any(x in key for x in ('especific','especializ','obrigatori'))
            if reproductive and special and value not in (False,None,[],{},'') and any(x in key for x in ('agente','polinizador','vetor','condic')):
                found.append({'path':path,'value':value});return
            # A conditional "podem impedir" is not an exclusive biological rule.
            if any(x in key for x in ('observacao','descricao','pistas','risco','uso_potencial')):return
            if ('poliniz' in text or 'fecund' in text) and re.search(r'(?:obrigatori\w*|exclusiv\w*|depende de|somente por|apenas por)',text) and not ('podem impedir' in text):
                found.append({'path':path,'value':value})
    walk(obj,'');return found


@lru_cache(maxsize=1)
def catalog_obligations():
    raw=(catalog.ROOT/'datasets/02_Flora'/catalog.SOURCE).read_bytes()
    if sha256(raw).hexdigest()!=catalog.SHA:raise ValueError('S1 requires the pinned v22 source')
    data=json.loads(raw.decode('utf-8-sig'));result={}
    for sp in data['flora']:
        constraints=specialized_requirements(sp)
        if constraints:result[sp['id']]=constraints
    return result


def rules():
    return {'revision':1,'policy':'abstract_conspecific_mature_pair_without_specialized_agent',
        'self_fertilization_assumed':False,'minimum_mature_producers':2,'viability_days':180,
        'unknown_genetics':'species_identity_and_maturity_are_gameplay_compatibility_not_measured_genetics',
        'absence_of_specific_vector_is_not_obligate_fauna':True,'pollinator_entities_created':False}


def authorization(sp):
    if sp.magic=='excepcional':return False,'exact_canonical_authorization_missing'
    required=specialized_requirements(json.loads(sp.growth_json or '{}'))+specialized_requirements(json.loads(sp.extreme_json or '{}'))
    required+=catalog_obligations().get(sp.id,[])
    if required:return False,'explicit_specialized_agent_or_condition_missing'
    strategy=normalized(json.loads(sp.growth_json or '{}').get('estrategia_reprodutiva_proposta',''))
    if 'sementes' not in strategy:return False,'sexual_strategy_not_declared'
    return True,None


def header(db,cid,base_signature=None):
    row=db.get(Policy,cid,populate_existing=True)
    if row is None:return None
    d=row.descriptor
    if (checksum(d)!=row.descriptor_checksum or checksum(d)[:24]!=row.signature or d.get('rules')!=rules() or
        d.get('flora_sha256')!=catalog.SHA or d.get('obligations_checksum')!=checksum(catalog_obligations()) or (base_signature is not None and d['L2_signature']!=base_signature)):
        raise ValueError('S1 authority corrupted or incompatible')
    return row


def initialize_sexual_policy(db,cid,*,experimental=False):
    from . import renewal as l2,service,lifecycle as life
    if experimental is not True:raise ValueError('Explicit experimental S1 activation required')
    v=service.context(db,cid);p=l2.header(db,cid,v)
    if p is None:raise ValueError('Explicit L2 required before S1')
    old=header(db,cid,p.signature)
    if old:return old
    service._fence(db,cid)
    with db.begin_nested():
        l2.advance(db,cid,v)
        obligations=catalog_obligations()
        d={'kind':'L2_sexual_extension_S1','revision':1,'L2_signature':p.signature,'activation_minute':life.now(db,cid),
            'flora_sha256':v.catalog.source_hash,'obligations_checksum':checksum(obligations),'rules':rules()}
        row=Policy(campaign_id=cid,signature=checksum(d)[:24],descriptor=d,descriptor_checksum=checksum(d));db.add(row);db.flush()
        for pop in db.query(l2.Renewing).filter_by(campaign_id=cid):
            data=deepcopy(pop.data);sp=v.catalog.species[pop.species_id]
            data['profile']=extend_profile(data['profile'],sp,row);l2._put(pop,data)
        db.flush();return row


def extend_profile(profile,sp,policy):
    if policy is None or profile['blocked_reason']!='pollination_or_vector_or_propagule_mechanism_unconfirmed':return profile
    allowed,reason=authorization(sp)
    if not allowed:return {**profile,'S1_pending_reason':reason}
    return {**profile,'mechanism':'abstract_sexual_internal','blocked_reason':None,
        'sexual_policy_revision':1,'sexual_policy_signature':policy.signature,'sexual_effective_minute':policy.descriptor['activation_minute'],
        'minimum_mature_producers':2,'viability_minutes':rules()['viability_days']*1440,
        'compatibility_model':rules()['policy'],'pollinator_entities_created':False,
        'source':'v22_seed_strategy_plus_explicit_S1_sexual_abstraction_not_observed_pollination'}


def validate_profile(db,cid,profile):
    sig=profile.get('sexual_policy_signature')
    if not sig:return
    policy=header(db,cid)
    if policy is None or sig!=policy.signature:raise ValueError('Missing or mismatched S1 profile authority')


def compatible_mate(db,source,bank,parent_id,parent_point,v,cache):
    from . import renewal as l2
    key=('S1_mate',source.population_id,bank['id'],parent_id)
    if key in cache:return cache[key]
    c=l2._entity(db,source.campaign_id,l2.Community,source.community_id,v)
    pop=next(p for p in c.baseline['populations'] if p['species_id']==source.species_id)
    cohort=bank['cohort'];point=SurfacePoint(*parent_point)
    runtime=db.info.get(('L2_batch',source.campaign_id))
    if runtime is not None and hasattr(runtime,'mate_cohort'):
        _,excluded,children=runtime.mate_cohort(bank)
    else:excluded=set(cohort['excluded_founders']);children={x['slot']:x for x in cohort['mature_children']}
    from .service import eligibility_at
    candidates=[]
    for slot in l2._near_slots(c,pop,point):
        child=children.get(slot)
        if child:identifier=child['id'];q=SurfacePoint(*child['point'])
        elif not cohort['all_founders_dead'] and slot not in excluded:
            identifier='vgi:'+checksum([pop['population_id'],slot])[:32];q=l2._slot_point(c,pop,slot)
        else:continue
        if identifier==parent_id:continue
        distance=distance_m(v.environment.regional.terrain.plan.source.config,point,q)
        if distance<=source.data['profile']['dispersal_m']:candidates.append((distance,identifier,q))
    answer=None
    for distance,identifier,q in sorted(candidates,key=lambda x:x[:2]):
        eligible_key=(source.species_id,tuple(q.xyz))
        if eligible_key not in cache:cache[eligible_key]=eligibility_at(db,source.campaign_id,v,v.catalog.species[source.species_id],q)[0]=='eligible'
        if cache[eligible_key]:
            answer={'revision':1,'policy_signature':source.data['profile']['sexual_policy_signature'],'mate_id':identifier,
                'mate_point':list(q.xyz),'compatibility':'conspecific_mature_pair_S1','pollinator_entity':None};break
    cache[key]=answer;return answer
