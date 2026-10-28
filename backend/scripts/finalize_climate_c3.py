"""Final C3 decision: E1 cross-tabs, two bounded calibration trials and spatial witnesses."""
from collections import Counter,defaultdict,deque
import csv
import json
from math import ceil
from pathlib import Path
from types import SimpleNamespace
import time
from PIL import Image,ImageDraw
from app.game.world.genesis.climate.v3 import ClimateConfigV3R1,accounting_summary
from app.game.world.genesis.climate.plan import load_climate_plan
from app.game.world.genesis.climate.calibration import report
from app.game.world.genesis.environment.adapter import EnvironmentSampler
from app.game.world.genesis.environment.config import EnvironmentConfigC3
from app.game.world.genesis.environment.preview import fonts,write_region_preview
from app.game.world.genesis.sphere_topology import CellKey,SurfacePoint,neighbor,DIRECTIONS
from app.game.world.genesis.sphere_metric import distance_m,_unit,_quantize
from app.game.world.genesis.terrain.field import checksum
from scripts.audit_climate_after_e1 import sample_grid,summarize_rows,forest_ids,write_maps
from scripts.validate_environment import environment_inputs,regional_window,persistence_demo
from scripts.validate_regional_geology import land_windows
from scripts.compare_climate_versions import solve
from scripts.recalibrate_climate import regional_comparisons,compare_image,potential_comparison

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'artifacts/climate-c3-final'
SEEDS=(42,0,7,2026,12345)


def ratio_class(row):
    p=row['P_over_PET']
    return 'PET0' if p is None else 'hyperarid' if p<.05 else 'arid' if p<.2 else 'semiarid' if p<.5 else 'moderate' if p<1 else 'humid'


def dry_primary(row):
    p=row['primary_potential'] or ''
    return 'DESERTO' in p or p=='EV-BIO-ESTEPE'


def favorable(row):
    return row['land'] and row['P_over_PET'] is not None and row['P_over_PET']>=.5 and row['temperature_c']>=0 and bool(forest_ids().intersection(row['eligible']))


def warm_humid(row):
    return row['land'] and row['P_over_PET'] is not None and row['P_over_PET']>=1 and row['temperature_c']>=5


def cross_matrix(rows):
    land=[r for r in rows if r['land']];area=sum(r['solid_angle'] for r in land)
    groups=defaultdict(lambda:[0,0.0]);dry=Counter();overlap=0.0;semantic=Counter()
    for r in land:
        rain=r['rain_mm'];t=r['temperature_c']
        rain_bin='0-100' if rain<100 else '100-250' if rain<250 else '250-500' if rain<500 else '500-1000' if rain<1000 else '1000-2000' if rain<2000 else '2000+'
        temp_bin='<-10' if t<-10 else '-10-0' if t<0 else '0-10' if t<10 else '10-20' if t<20 else '20+'
        key=(ratio_class(r),rain_bin,temp_bin,r['primary_potential'] or 'unclassified')
        groups[key][0]+=1;groups[key][1]+=r['solid_angle']
        if dry_primary(r):
            dry[ratio_class(r)]+=r['solid_angle']/area
            if forest_ids().intersection(r['eligible']):overlap+=r['solid_angle']/area
            if warm_humid(r):semantic['warm_humid_dry_primary']+=1
            if r['P_over_PET'] is not None and r['P_over_PET']>.45 and 'DESERTO' in (r['primary_potential'] or '') and r['primary_potential']!='EV-BIO-DESERTO_POLAR':
                semantic['nonpolar_desert_above_0_45']+=1
        if r['primary_potential'] and r['primary_potential'] not in r['eligible']:semantic['ineligible_primary']+=1
    return {'matrix':[{'P_PET_class':k[0],'rain_bin_mm':k[1],'temperature_bin_c':k[2],'primary':k[3],
                'count':v[0],'land_area_fraction':v[1]/area} for k,v in sorted(groups.items())],
        'dry_primary_area_by_ratio':dict(dry),'dry_primary_with_forest_eligible_area_fraction':overlap,
        'semantic_flags':dict(semantic),'scope':'sampled land; mutually exclusive matrix bins; not actual vegetation'}


def sampled_components(rows,predicate=favorable,radius=63710000):
    lookup={CellKey(*r['cell']):r for r in rows};active={k for k,r in lookup.items() if predicate(r)};unseen=set(active);components=[]
    while unseen:
        start=min(unseen);queue=deque([start]);unseen.remove(start);found=[]
        while queue:
            key=queue.popleft();found.append(key)
            for direction in DIRECTIONS:
                nxt=neighbor(key,direction)
                if nxt in unseen:unseen.remove(nxt);queue.append(nxt)
        components.append(found)
    components.sort(key=lambda c:(-sum(lookup[k]['solid_angle'] for k in c),min(c)))
    result=[];config=SimpleNamespace(radius_m=radius)
    for comp in components:
        start=min(comp)
        far=lambda a:max(comp,key=lambda b:(distance_m(config,SurfacePoint(*lookup[a]['point']),SurfacePoint(*lookup[b]['point'])),b))
        a=far(start);b=far(a);area=sum(lookup[k]['solid_angle'] for k in comp)
        result.append({'cells':len(comp),'solid_angle':area,'area_km2_estimate':area*radius*radius/1e6,
            'extent_lower_bound_km':distance_m(config,SurfacePoint(*lookup[a]['point']),SurfacePoint(*lookup[b]['point']))/1000,
            'faces':sorted({k.face for k in comp}),'endpoints':[lookup[a]['point'],lookup[b]['point']],
            'endpoint_cells':[[a.face,a.level,a.x,a.y],[b.face,b.level,b.x,b.y]]})
    favorable_area=sum(lookup[k]['solid_angle'] for k in sorted(active))
    land_area=sum(lookup[k]['solid_angle'] for k in sorted(lookup) if lookup[k]['land'])
    return {'component_count':len(result),'favorable_cells':len(active),'favorable_solid_angle':favorable_area,
        'favorable_land_fraction':favorable_area/land_area if land_area else None,'components':result[:10],
        'coverage':'center-sampled four-neighbor graph across exact cube seams; not exact continuous polygons'}


def verify_component_path(sampler,rows,components):
    if not components['components']:return {'probes':0,'longest_verified_run_km':0}
    lookup={CellKey(*r['cell']):r for r in rows};active={k for k,r in lookup.items() if favorable(r)}
    largest=components['components'][0];start,end=(CellKey(*k) for k in largest['endpoint_cells'])
    previous={start:None};queue=deque([start])
    while queue and end not in previous:
        k=queue.popleft()
        for direction in DIRECTIONS:
            nxt=neighbor(k,direction)
            if nxt in active and nxt not in previous:previous[nxt]=k;queue.append(nxt)
    path=[];k=end
    while k is not None:path.append(k);k=previous[k]
    path.reverse();probes=[]
    for a,b in zip(path,path[1:]):
        p,q=SurfacePoint(*lookup[a]['point']),SurfacePoint(*lookup[b]['point'])
        count=max(1,ceil(distance_m(sampler.regional.terrain.plan.source.config,p,q)/250000))
        u,v=_unit(p),_unit(q)
        for i in range(count):
            point=p if i==0 else _quantize(tuple((x*(count-i)+y*i)/count for x,y in zip(u,v)))
            s=sampler.sample(point);f=s['logical_facts'];eligible=[r['environment_id'] for r in s['results'] if r['state']=='elegivel']
            row={'point':list(point.xyz),'land':f['terreno.evidencia_superficie_continental'],'P_over_PET':f['clima.indice_aridez'],
                'temperature_c':f['clima.temperatura_media_anual_c'],'rain_mm':f['clima.precipitacao_anual_mm'],'eligible':eligible}
            row['favorable']=favorable(row);probes.append(row)
    last=lookup[end];probes.append({**last,'favorable':favorable(last)})
    longest=run=0.0
    for a,b in zip(probes,probes[1:]):
        if a['favorable'] and b['favorable']:
            run+=distance_m(sampler.regional.terrain.plan.source.config,SurfacePoint(*a['point']),SurfacePoint(*b['point']))/1000
            longest=max(longest,run)
        else:run=0.0
    return {'probes':len(probes),'failed_probes':sum(not p['favorable'] for p in probes),'longest_verified_run_km':longest,
        'path_cells':len(path),'scope':'probes spaced <=250km; not proof of every intervening metre','samples':probes}


def ranking_examples(sampler,rows):
    choices={}
    for r in rows:
        if not r['land'] or not dry_primary(r):continue
        label=('PET0' if r['P_over_PET'] is None else 'humid_polar' if r['P_over_PET']>=1 else
            'dry_with_forest_overlap' if forest_ids().intersection(r['eligible']) else 'dry_only')
        choices.setdefault(label,r)
    records=[]
    for label,r in sorted(choices.items()):
        sample=sampler.sample(SurfacePoint(*r['point']))
        covers=sorted((x for x in sample['results'] if x['state']=='elegivel' and x['role'] in ('cobertura_principal','cobertura_costeira')),
            key=lambda x:(-x['score_ppm'],x['environment_id']))
        records.append({'reason':label,'point':r['point'],'climate':{k:r[k] for k in ('rain_mm','pet_mm','P_over_PET','temperature_c')},
            'primary':sample['primary_potential'],'ranked_eligible':covers[:10],'vegetation_established':None})
    return records


def fixed_path_audit(sampler,points):
    """Compare exactly the same spatial corridor, not different winning components."""
    probes=[]
    for xyz in points:
        s=sampler.sample(SurfacePoint(*xyz));f=s['logical_facts']
        r={'point':xyz,'land':f['terreno.evidencia_superficie_continental'],'P_over_PET':f['clima.indice_aridez'],
            'temperature_c':f['clima.temperatura_media_anual_c'],'eligible':[x['environment_id'] for x in s['results'] if x['state']=='elegivel']}
        r['favorable']=favorable(r);probes.append(r)
    longest=run=0.0
    for a,b in zip(probes,probes[1:]):
        if a['favorable'] and b['favorable']:
            run+=distance_m(sampler.regional.terrain.plan.source.config,SurfacePoint(*a['point']),SurfacePoint(*b['point']))/1000;longest=max(longest,run)
        else:run=0.0
    return {'probes':len(probes),'failed_probes':sum(not p['favorable'] for p in probes),'longest_verified_run_km':longest,
        'scope':'same R1-55 corridor for every configuration; <=250km probes, not every metre'}


def persist_recommendation(folder):
    original=environment_inputs(42,63710000);data=json.loads((folder/'R1-55-plan.json').read_text())
    plan=load_climate_plan(data,original.climate.source_signature,original.h1.signature,63710000,original.climate.sea_level_m)
    sampler=EnvironmentSampler(original.regional,original.h1,plan,EnvironmentConfigC3());examples={}
    for r in json.loads((folder/'R1-55-samples.json').read_text()):
        if r['land'] and r['P_over_PET'] is not None:
            if r['P_over_PET']<.05:examples.setdefault('dry',sampler.sample(SurfacePoint(*r['point'])))
            if warm_humid(r):examples.setdefault('warm_humid',sampler.sample(SurfacePoint(*r['point'])))
        if len(examples)==2:break
    return persistence_demo(sampler,examples,folder)


def save_stage(folder,name,rows,sampler,seed):
    groups=summarize_rows(rows);matrix=cross_matrix(rows)
    comps=sampled_components(rows);humid=sampled_components(rows,warm_humid)
    result={'groups':groups,'cross_matrix':matrix,'favorable_components':comps,'warm_humid_components':humid,
        'climate_signature':sampler.climate.signature,'environment_signature':sampler.signature}
    with (folder/f'{name}-matrix.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(matrix['matrix'][0]));writer.writeheader();writer.writerows(matrix['matrix'])
    (folder/f'{name}-samples.json').write_text(json.dumps(rows,separators=(',',':')),encoding='utf-8')
    if seed==42:
        result['ranking_examples']=ranking_examples(sampler,rows)
        result['spatial_path']=verify_component_path(sampler,rows,comps)
    return result


def spatial_comparison(stages,path,seed):
    image=Image.new('RGB',(1530,1250),'#101e29');draw=ImageDraw.Draw(image);font,small=fonts()
    draw.text((20,15),f'Climate comparison / seed {seed} / favorable land, not established vegetation',font=font,fill='white')
    for i,(name,rows) in enumerate(stages.items()):
        y0=70+i*275;draw.text((20,y0),name+' / P/PET >=0.5, mean >=0 C, forest profile eligible',font=small,fill='white')
        for face in range(6):
            tile=Image.new('RGB',(32,32));px=tile.load()
            for y in range(32):
                for x in range(32):
                    r=rows[face*1024+y*32+x];px[x,y]=(45,160,130) if favorable(r) else (65,77,86) if r['land'] else (27,68,111)
            image.paste(tile.resize((220,220),Image.Resampling.NEAREST),(20+250*face,y0+25))
    draw.text((20,1200),'Center samples only. Components cross exact face seams; sub-cell continuity is checked separately by path probes.',font=small,fill='white')
    image.save(path)


def run():
    OUTPUT.mkdir(parents=True,exist_ok=True);cases=[]
    for seed in SEEDS:
        folder=OUTPUT/f'seed-{seed}';folder.mkdir(exist_ok=True);original=environment_inputs(seed,63710000)
        data=json.loads((ROOT/f'artifacts/climate-recalibration-0.9.1/seed-{seed}/c3-plan.json').read_text())
        old=load_climate_plan(data,original.climate.source_signature,original.h1.signature,63710000,original.climate.sea_level_m)
        assert solve(original.climate,old.config)==old
        source_hash=checksum(original.regional.terrain.plan.source.to_dict()),checksum(original.regional.macro.to_dict())
        stages={};stage_rows={};samplers={}
        for name,sampler,path in (
            ('C2',original,ROOT/f'artifacts/climate-audit-after-e1/seed-{seed}/samples-level-5.json'),
            ('C3-45',EnvironmentSampler(original.regional,original.h1,old,EnvironmentConfigC3()),ROOT/f'artifacts/climate-recalibration-0.9.1/seed-{seed}/c3-samples.json')):
            rows=json.loads(path.read_text());stage_rows[name]=rows;samplers[name]=sampler;stages[name]=save_stage(folder,name,rows,sampler,seed)
        if seed==42:
            anchor=SurfacePoint(*stages['C3-45']['favorable_components']['components'][0]['endpoints'][0])
            for label,sampler in (('C2',original),('C3-45',EnvironmentSampler(original.regional,original.h1,old,EnvironmentConfigC3()))):
                window,_=regional_window(sampler,anchor,width_m=4096000,intervals=16)
                (folder/f'{label}-mosaic.json').write_text(json.dumps(window,indent=2),encoding='utf-8')
                write_region_preview(window,folder/f'{label}-mosaic.png',seed=seed)
        for name,recycling in (('R1-45',450000),('R1-55',550000)):
            config=ClimateConfigV3R1(land_recycling_ppm=recycling);started=time.perf_counter();plan=solve(original.climate,config)
            kernel_seconds=time.perf_counter()-started;sampler=EnvironmentSampler(original.regional,original.h1,plan,EnvironmentConfigC3())
            saved_plan=folder/f'{name}-plan.json';saved_rows=folder/f'{name}-samples.json'
            reused=saved_plan.exists() and saved_rows.exists()
            if reused:
                pinned=load_climate_plan(json.loads(saved_plan.read_text()),plan.source_signature,plan.hydrology_signature,plan.radius_m,plan.sea_level_m)
                if pinned!=plan:raise ValueError('Cached trial differs from the exact replay')
                rows=json.loads(saved_rows.read_text());query_seconds=None
            else:
                started=time.perf_counter();rows,_=sample_grid(sampler,5);query_seconds=time.perf_counter()-started
            assert len(rows)==6144
            assert all(a['point']==b['point'] and a['temperature_c']==b['temperature_c'] and a['pet_mm']==b['pet_mm'] for a,b in zip(rows,stage_rows['C2']))
            stage_rows[name]=rows;samplers[name]=sampler;stages[name]=save_stage(folder,name,rows,sampler,seed)
            stages[name].update(config=config.model_dump(),kernel_seconds=kernel_seconds,queries_seconds=query_seconds,reused_frozen_samples=reused,
                accounting=accounting_summary(plan),native=report(plan))
            payload=plan.to_dict();assert load_climate_plan(json.loads(json.dumps(payload)),plan.source_signature,plan.hydrology_signature,plan.radius_m,plan.sea_level_m)==plan
            (folder/f'{name}-plan.json').write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8')
            write_maps(rows,5,seed,folder/f'{name}.png',climate_label=name)
            compare_image(ROOT/f'artifacts/climate-recalibration-0.9.1/seed-{seed}/c3.png',folder/f'{name}.png',folder/f'{name}-comparison.png')
            (folder/name).mkdir(exist_ok=True)
            stages[name]['regional_comparisons']=regional_comparisons(EnvironmentSampler(original.regional,original.h1,old,EnvironmentConfigC3()),sampler,folder/name,before_label='C3-45',after_label=name)
            if seed==42:
                # Same 4096km anchor for all candidate views, defined by baseline favorable component.
                anchor=SurfacePoint(*stages['C3-45']['favorable_components']['components'][0]['endpoints'][0])
                window,_=regional_window(sampler,anchor,width_m=4096000,intervals=16)
                (folder/f'{name}-mosaic.json').write_text(json.dumps(window,indent=2),encoding='utf-8')
                write_region_preview(window,folder/f'{name}-mosaic.png',seed=seed)
            g=stages[name]['groups']['surface/land']
            print(json.dumps({'seed':seed,'candidate':name,'rain':g['rain_mm']['mean'],'humid':g['index_area_fractions'].get('humid',0),
                'forest_potential':g['any_forest_eligible_area_fraction'],'forest_primary':g['forest_primary_area_fraction']}),flush=True)
        spatial_comparison(stage_rows,folder/'spatial-comparison.png',seed)
        case={'seed':seed,'radius_m':63710000,'stages':stages,'source_geography_unchanged':source_hash==(
            checksum(original.regional.terrain.plan.source.to_dict()),checksum(original.regional.macro.to_dict()))}
        if seed==42:
            points=[p['point'] for p in stages['R1-55']['spatial_path']['samples']]
            case['fixed_path_comparison']={name:fixed_path_audit(sampler,points) for name,sampler in samplers.items()}
        (folder/'report.json').write_text(json.dumps(case,indent=2),encoding='utf-8');cases.append(case)
    (OUTPUT/'suite.json').write_text(json.dumps({'cases':cases,'E1_changed':False,'real_saves_changed':False,
        'water_C3_enabled':False,'candidate_profiles_explicit':True,'recommended':'R1-55',
        'recommended_config':ClimateConfigV3R1(land_recycling_ppm=550000).model_dump(),
        'persistence_proof':persist_recommendation(OUTPUT/'seed-42')},indent=2),encoding='utf-8')


if __name__=='__main__':run()
