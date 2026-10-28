"""VSR1 derived structure from persistent occupants, never a Vg2 recalibration.

Adult footprint and architecture come from the existing patch. Crown area scales
with squared relative height for a growing individual. Missing slots contribute
zero; no quota, rain, leaf stock, or inferred vegetation is added.
"""
from . import service,renewal as l2,lifecycle as life
from ..terrain.field import checksum

Q=1000000


def measure_community(db,cid,community_id,*,v=None,advance=True,original=False):
    v=v or service.context(db,cid)
    if advance and not original:l2.advance(db,cid,v)
    c=db.get(l2.Community,(cid,community_id));service._validate_community(c,v)
    rows={r.individual_id:r for r in db.query(l2.Individual).filter_by(campaign_id=cid,community_id=community_id)}
    natives={r.population_id:r for r in db.query(l2.Population).filter_by(campaign_id=cid)} if not original else {}
    minute=life.now(db,cid);populations=[];basis=[]
    for pop in c.baseline['populations']:
        native=natives.get(pop['population_id']);capacity=pop['founder_count'];adult_height=pop['height_cm']
        if native:
            if checksum(native.data)!=native.data_checksum:raise ValueError('VSR1 occupancy corrupted')
            slots=native.data['slots'];founders=0 if native.data.get('cleared_minute') is not None else capacity-len(slots)
        else:slots={};founders=capacity
        weights=founders*Q;living=founders;height_sum=founders*adult_height;weighted_height=founders*adult_height*Q
        strata={'canopy':0,'shrub':0,'ground':0};stages={'germinating':0,'young':0,'adult':founders}
        category=lambda h:'canopy' if h>=500 else 'shrub' if h>=100 else 'ground'
        strata[category(adult_height)]=founders*Q;signature_items=[]
        for slot,entry in slots.items():
            identifier=entry.get('occupant')
            if not identifier:continue
            child=rows.get(identifier)
            if entry.get('ga2_child'):
                from .renewal_gameplay import checked_record,stage_record
                rec=checked_record(entry);s={'alive':True,'life':stage_record(rec,minute)}
                if child is not None:
                    service._validate_individual(child)
                    if not child.state['alive']:raise ValueError('VSR1 dead GA2 occupant')
            else:
                if child is None:raise ValueError('VSR1 missing occupant')
                service._validate_individual(child)
                s=life.project(child.baseline,child.state,minute,v.catalog.species[pop['species_id']])
            if not s['alive']:raise ValueError('VSR1 dead individual occupies a living slot')
            h=s['life']['height_cm'];stage=s['life']['maturity'];living+=1;height_sum+=h;stages[stage]+=1
            area=min(Q,h*h*Q//max(1,adult_height*adult_height));weights+=area;weighted_height+=h*area;strata[category(h)]+=area
            signature_items.append([identifier,slot,h,stage,s['life']['birth_minute']])
        cover=pop['cover_ppm']*weights//(capacity*Q)
        strata_cover={k:pop['cover_ppm']*w//(capacity*Q) for k,w in strata.items()}
        # Preserve integer conservation despite independent strata rounding.
        remainder=cover-sum(strata_cover.values())
        if remainder:strata_cover[max(strata,key=strata.get)]+=remainder
        footprint=max(1,adult_height*adult_height//40000) if pop['kind']=='arvore' else 1
        populations.append({'species_id':pop['species_id'],'population_id':pop['population_id'],'kind':pop['kind'],
            'capacity':capacity,'living':living,'surviving_founders':founders,'stages':stages,'cover_ppm':cover,
            'original_cover_ppm':pop['cover_ppm'],'mean_height_cm':height_sum//max(1,living),'height_sum_cm':height_sum,
            'cover_weighted_height_cm':weighted_height//max(1,weights),'strata_cover_ppm':strata_cover,
            'density_per_ha':living*10000//c.baseline['patch_area_m2'],'adult_footprint_reference_m2':footprint,
            'relative_crown_area_sum_ppm':weights})
        basis.append([pop['population_id'],founders,sorted(signature_items)])
    total=sum(p['cover_ppm'] for p in populations);count=sum(p['living'] for p in populations);trees=[p for p in populations if p['kind']=='arvore']
    result={'structure_version':'VSR1','authority':'derived_from_persistent_L1_L2_occupancy','community_id':community_id,
        'minute':minute,'original_reference':original,'baseline_checksum':c.baseline_checksum,'populations':populations,
        'cover_ppm':total,'clearing_ppm':Q-total,'original_cover_ppm':c.baseline['cover_ppm'],'living':count,
        'density_per_ha':count*10000//c.baseline['patch_area_m2'],
        'mean_height_cm':sum(p['height_sum_cm'] for p in populations)//max(1,count),
        'cover_weighted_height_cm':sum(p['cover_weighted_height_cm']*p['cover_ppm'] for p in populations)//max(1,total),
        'tree_living':sum(p['living'] for p in trees),'tree_cover_ppm':sum(p['cover_ppm'] for p in trees),
        'tree_mean_height_cm':sum(p['height_sum_cm'] for p in trees)//max(1,sum(p['living'] for p in trees)),
        'strata_cover_ppm':{k:sum(p['strata_cover_ppm'][k] for p in populations) for k in ('canopy','shrub','ground')},
        'assumptions':'baseline_architecture_and_height_squared_crown_area_not_measured_foliage_or_full_rendering',
        'Vg2_baseline_modified':False,'public_map_export':False}
    result['measurement_signature']=checksum([1,c.baseline_checksum,minute,basis]);return result
