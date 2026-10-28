"""Phase 0.9.1 offline C3 experiments. Never changes campaign databases."""
import json
from pathlib import Path
import statistics
import time
import tracemalloc
from collections import Counter
from PIL import Image,ImageDraw
from app.game.world.genesis.climate.v3 import ClimateConfigV3,accounting_summary
from app.game.world.genesis.climate.calibration import report
from app.game.world.genesis.climate.plan import load_climate_plan
from app.game.world.genesis.climate.query import sample_climate
from app.game.world.genesis.environment.adapter import EnvironmentSampler
from app.game.world.genesis.environment.config import EnvironmentConfigC3
from app.game.world.genesis.environment.preview import fonts
from app.game.world.genesis.terrain.field import checksum
from scripts.compare_climate_versions import solve
from scripts.validate_environment import environment_inputs,regional_window,persistence_demo
from scripts.audit_climate_after_e1 import sample_grid,write_maps,summarize_rows,forest_ids
from scripts.validate_regional_geology import land_windows

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'artifacts/climate-recalibration-0.9.1'
CANDIDATES={'distance_only':0,'recycling_35':350000,'recycling_45':450000,'recycling_65':650000}


def regional_comparisons(original,experimental,folder,*,before_label='C2',after_label='C3'):
    """Two predeclared J1 anchor windows per seed; compare actual E1 secondaries."""
    summaries=[]
    for i,center in enumerate(land_windows(original.regional)[:2]):
        pair={}
        for name,sampler in ((before_label,original),(after_label,experimental)):
            window,_=regional_window(sampler,center,width_m=1024000,intervals=12)
            secondary=Counter(e for row in window['samples'] for p in row for e in p['secondary_potential'])
            pair[name]={'primary_counts':window['primary_counts'],'secondary_counts':dict(secondary),
                'ecotone_probes':window['ecotone_samples'],'transition_edges':window['transition_edges'],
                'primary_diversity':window['primary_diversity'],'eligible_diversity':window['eligible_diversity']}
            (folder/f'regional-{i}-{name}.json').write_text(json.dumps(window,indent=2),encoding='utf-8')
        summaries.append({'anchor':list(center.xyz),'width_m':1024000,'points_per_version':144,**pair})
    return summaries


def compare_image(before,after,path):
    a,b=Image.open(before),Image.open(after)
    combined=Image.new('RGB',(a.width+b.width,max(a.height,b.height)),'#101e29')
    combined.paste(a,(0,0));combined.paste(b,(a.width,0));combined.save(path)


def distance_profile(before,after,path,seed):
    image=Image.new('RGB',(1200,500),'#101e29');d=ImageDraw.Draw(image);font,small=fonts()
    d.text((20,20),f'C2 -> C3 / seed {seed} / land area-weighted annual precipitation mm',font=font,fill='white')
    for i,key in enumerate(('0-1000km','1000-3000km','3000-10000km','10000km+')):
        y=100+i*85;d.text((20,y),key,font=small,fill='white')
        for offset,groups,c in ((0,before,'#5e9bcd'),(30,after,'#e49a6a')):
            value=groups.get('ocean_distance/'+key,{}).get('rain_mm',{}).get('mean',0)
            d.rectangle((200,y+offset,200+min(850,int(value*.65)),y+offset+20),fill=c)
            d.text((210+min(850,int(value*.65)),y+offset),f'{value:.1f}',font=small,fill='white')
    d.text((20,460),'Blue=C2, orange=C3; identical horizontal scale. Ocean distances are macro proxies.',font=small,fill='white')
    image.save(path)


def potential_comparison(before,after,path,seed):
    image=Image.new('RGB',(1530,1210),'#101e29');draw=ImageDraw.Draw(image);font,small=fonts()
    draw.text((20,15),f'C2 -> C3 / seed {seed} / aridity classes and OVERLAPPING forest potential',font=font,fill='white')
    palette=((100,71,49),(178,117,70),(224,184,100),(146,185,148),(50,145,167))
    for panel,(version,rows,is_forest) in enumerate((('C2',before,False),('C3',after,False),('C2',before,True),('C3',after,True))):
        y0=70+panel*270;label='any forest profile eligible; not actual trees' if is_forest else 'hyperarid / arid / semiarid / moderate / humid by P/PET'
        draw.text((20,y0),version+' / '+label,font=small,fill='white')
        for face in range(6):
            tile=Image.new('RGB',(32,32));px=tile.load()
            for y in range(32):
                for x in range(32):
                    r=rows[face*1024+y*32+x];p=r['P_over_PET']
                    if not r['land']:c=(27,68,111)
                    elif is_forest:c=(68,175,125) if forest_ids().intersection(r['eligible']) else (66,78,87)
                    elif p is None:c=(120,120,135)
                    else:c=palette[0 if p<.05 else 1 if p<.2 else 2 if p<.5 else 3 if p<1 else 4]
                    px[x,y]=c
            image.paste(tile.resize((220,220),Image.Resampling.NEAREST),(20+250*face,y0+25))
    draw.text((20,1160),'Forest eligibility overlaps other habitats. Dark blue=marine reference; grey=undefined energy or no forest potential.',font=small,fill='white')
    image.save(path)


def run():
    OUTPUT.mkdir(parents=True,exist_ok=True);results=[]
    old_suite=json.loads((ROOT/'artifacts/climate-audit-after-e1/suite.json').read_text())
    for seed in (42,0,7,2026,12345):
        folder=OUTPUT/f'seed-{seed}';folder.mkdir(exist_ok=True)
        original=environment_inputs(seed,63710000);c2=original.climate
        old=next(c for c in old_suite['cases'] if c['seed']==seed)
        assert old['environment_signature']==original.signature and old['climate_signature']==c2.signature
        assert solve(c2,c2.config)==c2
        physical_before=checksum(original.regional.macro.to_dict()),checksum(original.regional.terrain.plan.source.to_dict()),checksum(c2.to_dict())
        candidates=[];selected=None;times=[]
        for name,fraction in CANDIDATES.items():
            start=time.perf_counter();candidate=solve(c2,ClimateConfigV3(land_recycling_ppm=fraction));elapsed=time.perf_counter()-start
            summary=report(candidate)
            candidates.append({'name':name,'config':candidate.config.model_dump(),'signature':candidate.signature,
                'kernel_seconds':elapsed,'groups':summary['groups'],'transport_audit':summary['transport_audit'],
                'residual_ppm':list(candidate.transport_residual_ppm),'accounting':accounting_summary(candidate)})
            if fraction==450000:selected=candidate
        assert selected.sea_temperature_centi_c==c2.sea_temperature_centi_c
        assert selected.wind_milli_m_s==c2.wind_milli_m_s and selected.heights==c2.heights
        payload=json.dumps(selected.to_dict(),separators=(',',':'))
        assert load_climate_plan(json.loads(payload),c2.source_signature,c2.hydrology_signature,c2.radius_m,c2.sea_level_m)==selected
        sampler=EnvironmentSampler(original.regional,original.h1,selected,EnvironmentConfigC3())
        started=time.perf_counter();rows,groups=sample_grid(sampler,5);query_seconds=time.perf_counter()-started
        baseline_rows=json.loads((ROOT/f'artifacts/climate-audit-after-e1/seed-{seed}/samples-level-5.json').read_text())
        assert [r['point'] for r in rows]==[r['point'] for r in baseline_rows]
        assert all(a['temperature_c']==b['temperature_c'] and a['pet_mm']==b['pet_mm'] for a,b in zip(rows,baseline_rows))
        before=summarize_rows(baseline_rows)
        (folder/'c3-plan.json').write_text(payload,encoding='utf-8')
        (folder/'c3-samples.json').write_text(json.dumps(rows,separators=(',',':')),encoding='utf-8')
        write_maps(baseline_rows,5,seed,folder/'c2.png')
        write_maps(rows,5,seed,folder/'c3.png',climate_label='C3 experimental')
        compare_image(folder/'c2.png',folder/'c3.png',folder/'comparison.png')
        distance_profile(before,groups,folder/'distance-profile.png',seed)
        potential_comparison(baseline_rows,rows,folder/'potential-comparison.png',seed)
        extra={}
        if seed==42:
            # Fixed previous witnesses, not new positions selected for a desirable result.
            from app.game.world.genesis.sphere_topology import SurfacePoint
            from app.game.world.genesis.environment.preview import write_region_preview
            for name in ('wet_warm','dry_warm'):
                p=SurfacePoint(*old['witnesses'][name]['point'])
                window,_=regional_window(sampler,p,width_m=1024000,intervals=12)
                extra[name]=window
                write_region_preview(window,folder/f'{name}-region.png',seed=seed)
            examples={}
            for row in rows:
                if row['land'] and row['eligible']:
                    examples.setdefault('land',sampler.sample(SurfacePoint(*row['point'])))
                    if any('FLORESTA' in e for e in row['eligible']):examples.setdefault('forest',sampler.sample(SurfacePoint(*row['point'])))
                if len(examples)==2:break
            extra['persisted']=persistence_demo(sampler,examples,folder)
        result={'seed':seed,'radius_m':63710000,'C2_signature':c2.signature,'C3_signature':selected.signature,
            'native_before':old['native_vertex_report'],
            'E1_C2_signature':original.signature,'E1_C3_signature':sampler.signature,'candidates':candidates,
            'before':before,'after':groups,'point_count':len(rows),'C3_payload_bytes':len(payload.encode()),
            'E1_queries_seconds':query_seconds,'regional_probes':extra,'temperature_PET_unchanged':True,
            'physical_sources_unchanged':physical_before==(checksum(original.regional.macro.to_dict()),checksum(original.regional.terrain.plan.source.to_dict()),checksum(c2.to_dict()))}
        result['regional_primary_secondary_comparison']=regional_comparisons(original,sampler,folder)
        (folder/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8');results.append(result)
        print(json.dumps({'seed':seed,'before_rain':before['surface/land']['rain_mm']['mean'],
            'after_rain':groups['surface/land']['rain_mm']['mean'],'dry_primary':groups['surface/land']['dry_primary_area_fraction'],
            'forest_eligible':groups['surface/land']['any_forest_eligible_area_fraction']}),flush=True)
    (OUTPUT/'suite.json').write_text(json.dumps({'cases':results,'selected':'recycling_45','runtime_enabled':False,
        'real_save_modified':False,'new_water_balances_enabled':False},indent=2),encoding='utf-8')


if __name__=='__main__':run()
