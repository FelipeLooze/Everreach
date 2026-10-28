"""S1 audit, real five-seed reproduction and VSR1 coverage recovery proofs."""
import argparse,json,sqlite3,time
from pathlib import Path
from collections import Counter
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.item import ItemInstance
from app.game.world.genesis.vegetation import renewal as l2,sexual as sex,lifecycle as life
from app.game.world.genesis.vegetation.catalog import load_flora_catalog
from app.game.world.genesis.vegetation.recovery_structure import measure_community
from app.game.world.genesis.vegetation.life_math import YEAR
from app.game.time.clock import advance_world_time
from app.tests.test_vegetation_renewal_l2 import setup
from scripts.validate_plant_resources import inputs


def audit(out):
    records=[];counts=Counter();types={}
    for sp in load_flora_catalog().species.values():
        old=l2.reproductive_profile(sp,sum(sp.height_cm)//2 if sp.height_cm else 100)
        allowed,reason=sex.authorization(sp);new=old['blocked_reason']=='pollination_or_vector_or_propagule_mechanism_unconfirmed' and allowed
        blocked=old['blocked_reason'] is not None and not new
        state='new_S1' if new else 'blocked' if blocked else 'existing_L2'
        counts[state]+=1;types.setdefault(sp.kind,Counter())[state]+=1
        records.append({'species_id':sp.id,'name':sp.name,'kind':sp.kind,'rarity':sp.rarity_name,'state':state,
            'L2_reason':old['blocked_reason'],'remaining_reason':reason if blocked else None,
            'strategy':old['canonical_strategy'],'inventory_item_created':False})
    summary={'counts':dict(counts),'by_kind':{k:dict(v) for k,v in types.items()},'source_sha256':load_flora_catalog().source_hash,
        'explicit_specialized_reproductive_obligations':sex.catalog_obligations(),
        'generic_cultivation_warning_is_not_a_specific_obligation':True,'source_v22_modified':False}
    (out/'species-authorization.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'authorization-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');return summary


def run(seed,kind,out):
    path=out/f'{kind}-seed-{seed}.json'
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    v=inputs(seed);engine=create_engine('sqlite:///:memory:');event.listen(engine,'connect',enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid,point,ind,part=setup(db,v,seed,kind);sid=ind.baseline['species_id'];c=db.get(l2.Community,(cid,ind.community_id))
        pop=next(p for p in c.baseline['populations'] if p['species_id']==sid)
        t=time.perf_counter();policy=sex.initialize_sexual_policy(db,cid,experimental=True);activation=time.perf_counter()-t
        original=measure_community(db,cid,ind.community_id,v=v,original=True)
        removals=(700 if seed==42 else pop['founder_count']*7//10) if kind=='arvore' else min(150,pop['founder_count']//2)
        l2.disturb_population(db,cid,ind.community_id,sid,removals,'proof-logging' if kind=='arvore' else 'sexual-flower' if kind=='flor' else 'field-recovery',experimental=True)
        results={};t0=life.now(db,cid);horizons=(0,1,5,10,20) if kind=='arvore' else (0,1,2)
        for years in horizons:
            advance_world_time(db,cid,t0+years*YEAR-life.now(db,cid));start=time.perf_counter();q=l2.query_population(db,cid,ind.community_id,sid);ecology=time.perf_counter()-start
            start=time.perf_counter();s=measure_community(db,cid,ind.community_id,v=v,advance=False);metrics=time.perf_counter()-start
            results[str(years)]={'population':q,'structure':s,'ecology_query_seconds':ecology,'structure_seconds':metrics,'total_seconds':ecology+metrics}
        events=[e for e in db.query(l2.Event).filter_by(campaign_id=cid,population_id=pop['population_id']) if e.payload.get('renewal_signature')]
        if kind=='arvore' and seed==42:assert results['10']['population']['living_count']==561
        record={'seed':seed,'kind':kind,'species_id':sid,'campaign_id':cid,'community_id':ind.community_id,'population_id':pop['population_id'],
            'capacity':pop['founder_count'],'removals':removals,'S1_signature':policy.signature,'L2_signature':l2.header(db,cid,v).signature,
            'S1_activation_seconds':activation,'original':original,'snapshots':results,'new_events':len(events),
            'event_statuses':dict(Counter(e.status for e in events)),'sexual_events':sum(bool(e.payload.get('sexual_authorization')) for e in events),
            'example_event':next((e.payload for e in events if e.payload.get('sexual_authorization')),events[0].payload if events else None),
            'inventory_instances':db.query(ItemInstance).count(),'radius_km':v.radius//1000}
        db.commit();raw=engine.raw_connection()
        with sqlite3.connect(out/f'{kind}-seed-{seed}.sqlite') as target:raw.driver_connection.backup(target)
        raw.close();path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    engine.dispose();return record


def figures(out,reports):
    from PIL import Image,ImageDraw
    from scripts.preview_vegetation import font
    tree=next(r for r in reports if r['seed']==42 and r['kind']=='arvore');sid=tree['species_id']
    fig=Image.new('RGB',(1500,900),'#f6f2e9');d=ImageDraw.Draw(fig)
    d.text((25,18),'EVERREACH 1.1.2 | seed 42 | cobertura e estrutura persistentes',font=font(25),fill='#213b31')
    d.text((25,59),'700 remocoes na populacao-alvo de 1.037 arvores. Outras populacoes do patch foram preservadas.',font=font(17),fill='#213b31')
    frames=[('Original',tree['original'])]+[('Devastada' if y=='0' else f'{y} ano(s)',tree['snapshots'][y]['structure']) for y in ('0','1','5','10','20')]
    original_pop=next(p for p in tree['original']['populations'] if p['species_id']==sid)
    for i,(label,s) in enumerate(frames):
        left=30+(i%3)*495;top=125+(i//3)*375;p=next(p for p in s['populations'] if p['species_id']==sid)
        d.text((left,top),label,font=font(23),fill='#213b31')
        # Values are actual crown-area and count ratios, never randomized colors.
        bars=[('Individuos vivos',p['living']/p['capacity'],'#527c9b'),('Area de copas',p['cover_ppm']/original_pop['cover_ppm'],'#347449')]
        for j,(name,value,color) in enumerate(bars):
            yy=top+50+j*55;d.text((left,yy),name,font=font(16),fill='#213b31');d.rectangle((left,yy+23,left+400,yy+39),fill='#ddd7ca');d.rectangle((left,yy+23,left+400*value,yy+39),fill=color)
            d.text((left+405,yy+17),f'{100*value:.1f}%',font=font(14),fill='#213b31')
        d.text((left,top+174),f"Vivos: {p['living']} | jovens: {p['stages']['young']} | adultos: {p['stages']['adult']}",font=font(15),fill='#213b31')
        d.text((left,top+205),f"Altura media presente: {p['mean_height_cm']/100:.2f} m",font=font(17),fill='#213b31')
        d.text((left,top+237),f"Cobertura da especie no patch: {p['cover_ppm']/10000:.2f}%",font=font(16),fill='#213b31')
        d.text((left,top+267),f"Cobertura total do patch: {s['cover_ppm']/10000:.2f}%",font=font(16),fill='#213b31')
        d.text((left,top+298),f"Densidade da especie: {p['density_per_ha']} / ha",font=font(16),fill='#213b31')
    d.text((25,867),'VSR1: area de copa derivada da arquitetura Vg2 e do quadrado do porte relativo. Nao e renderizacao nem recalibracao do teto.',font=font(15),fill='#213b31')
    fig.save(out/'forest-structure-recovery.png')


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('../artifacts/vegetation-stabilization-1.1.2'));p.add_argument('--seeds',nargs='+',type=int,default=[42,0,7,2026,12345]);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    counts=audit(a.out);reports=[]
    for seed in a.seeds:
        for kind in ('flor','graminea','arvore'):
            r=run(seed,kind,a.out);reports.append(r);last=r['snapshots'][str(20 if kind=='arvore' else 2)]['population'];print(seed,kind,r['capacity'],last['living_count'],r['new_events'],r['sexual_events'],flush=True)
    if 42 in a.seeds:figures(a.out,reports)
    summary={'seeds':a.seeds,'authorization':counts['counts'],'real_established':sum(r['event_statuses'].get('established',0) for r in reports),'sexual_events':sum(r['sexual_events'] for r in reports),'real_campaign_activation':False}
    (a.out/'quality-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
