"""Real GA1+L2 / GA1+GA2 populations. Only disposable proof databases."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import time

from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.game.time.clock import advance_world_time
from app.game.world.genesis.vegetation import lifecycle as life,renewal as l2,resources,service,sexual
from app.game.world.genesis.vegetation.growth_gameplay import LifeConfigGA1,pacing_class
from app.game.world.genesis.vegetation.renewal_gameplay import initialize_ga2,RenewalConfigGA2
from app.game.world.genesis.vegetation.recovery_structure import measure_community
from app.game.world.genesis.vegetation.life_math import DAY
from scripts.validate_plant_resources import inputs,actual_individual,candidates
from scripts.prove_vegetation import prepare

KINDS=('flor','erva','graminea','arbusto','tree','large_tree')


def setup(db,v,seed,kind,policy,config=None):
    cid=prepare(db,v);resources.initialize_resources(db,cid,experimental=True)
    if kind=='large_tree' and seed==42:
        point,ind,part=actual_individual(db,cid,v,seed,'arvore')
        assert pacing_class(v.catalog.species[ind.baseline['species_id']],LifeConfigGA1())=='large_tree'
    else:
        wanted='arvore' if kind in ('tree','large_tree') else kind;ind=None
        for point,sid in candidates(seed,wanted):
            if wanted=='arvore' and pacing_class(v.catalog.species[sid],LifeConfigGA1())!=kind:continue
            for slot in range(8):
                try:ind=service.materialize_individual(db,cid,point,sid,slot)
                except ValueError as exc:
                    if 'microsite unsupported' in str(exc):continue
                    raise
                break
            if ind is not None:break
        if ind is None:raise ValueError(f'No real {kind} at seed {seed}')
    life.initialize_life(db,cid,LifeConfigGA1(),experimental=True)
    if policy=='GA2':initialize_ga2(db,cid,config,experimental=True)
    else:
        l2.initialize_renewal(db,cid,experimental=True);sexual.initialize_sexual_policy(db,cid,experimental=True)
    return cid,point,ind


def backup(db,path):
    db.commit();raw=db.get_bind().raw_connection()
    with sqlite3.connect(path) as target:raw.driver_connection.backup(target)
    raw.close()


def run(seed,kind,policy,out):
    stem=f'{policy}-{kind}-{seed}';dest=out/f'{stem}.json'
    if dest.exists():return json.loads(dest.read_text(encoding='utf-8'))
    t=time.perf_counter();v=inputs(seed);cold=time.perf_counter()-t
    engine=create_engine('sqlite:///:memory:');event.listen(engine,'connect',enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        t=time.perf_counter();cid,point,ind=setup(db,v,seed,kind,policy);prep=time.perf_counter()-t
        sid=ind.baseline['species_id'];c=db.get(l2.Community,(cid,ind.community_id));pop=next(p for p in c.baseline['populations'] if p['species_id']==sid)
        original=measure_community(db,cid,c.community_id,v=v,original=True)
        count=700 if kind=='large_tree' and seed==42 else min(150,pop['founder_count']//2)
        selected=None
        if policy=='GA2':
            control=out/f'L2-{kind}-{seed}-initial.sqlite'
            if not control.exists():raise ValueError('Generate the L2 control before its matched GA2 experiment')
            with sqlite3.connect(control.resolve().as_uri()+'?mode=ro',uri=True) as source:
                receipts=[json.loads(r[0]) for r in source.execute('SELECT payload FROM genesis_vegetation_life_events WHERE status=?',('disturbance_applied',))]
            receipt=next(r for r in receipts if r.get('kind')=='L2_disturbance' and r['request'][1]==sid)
            selected=receipt['selected_slots'];assert type(selected)is list and len(selected)==count
        l2.disturb_population(db,cid,c.community_id,sid,count,'ga2-review-logging',experimental=True,_selected_slots=selected)
        start=life.now(db,cid);backup(db,out/f'{stem}-initial.sqlite')
        snapshots={}
        for day in (0,7,15,30,60,90,180,360):
            advance_world_time(db,cid,start+day*DAY-life.now(db,cid));t=time.perf_counter()
            q=l2.query_population(db,cid,c.community_id,sid);elapsed=time.perf_counter()-t;t=time.perf_counter()
            structure=measure_community(db,cid,c.community_id,v=v,advance=False);structure_s=time.perf_counter()-t
            assert q['living_count']<=pop['founder_count']
            snapshots[str(day)]={'population':q,'structure':structure,'update_and_query_seconds':elapsed,'structure_seconds':structure_s,
                                 'GA2_stats':db.info.get(('GA2_last_stats',cid))}
        events=[e for e in db.query(l2.Event).filter_by(campaign_id=cid,population_id=pop['population_id']) if e.payload.get('renewal_signature')]
        bankrow=db.get(l2.Renewing,(cid,pop['population_id']));marks=bankrow.data.get('ga2_marks',{})
        birth=min((e.due_minute for e in events if e.status=='established'),default=None)
        maturity=min((e.payload['ga2_child']['mature_minute'] for e in events if e.status=='established' and e.payload.get('ga2_signature')),default=None)
        to_days=lambda value:None if value is None else (value-start)/DAY
        result={'seed':seed,'kind':kind,'policy':policy,'species_id':sid,'name':v.catalog.species[sid].name,
                'campaign_id':cid,'community_id':c.community_id,'population_id':pop['population_id'],'capacity':pop['founder_count'],
                'removals':count,'signature':l2.header(db,cid,v).signature,'activation_minute':start,
                'first_opportunity_days':to_days(marks.get('first_opportunity_minute')),
                'first_propagule_days':to_days(marks.get('first_propagule_minute')),'first_birth_days':to_days(birth),
                'first_maturity_days':to_days(maturity),'original':original,'snapshots':snapshots,
                'persisted_birth_events':len(events),'event_states':dict(Counter(e.status for e in events)),
                'sexual_events':sum(bool(e.payload.get('sexual_authorization')) for e in events),
                'body_rows':db.query(l2.Individual).filter_by(campaign_id=cid).count(),
                'cold_context_seconds':cold,'preparation_seconds':prep,'real_save_modified':False}
        backup(db,out/f'{stem}.sqlite');dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(stem,'birth',result['first_birth_days'],'living180',snapshots['180']['population']['living_count'],
              'max_query_s',round(max(s['update_and_query_seconds'] for s in snapshots.values()),3),'bodies',result['body_rows'],flush=True)
    engine.dispose();return result


def figures(out):
    from PIL import Image,ImageDraw
    from scripts.preview_vegetation import font
    for kind in ('large_tree','flor'):
        paths=[out/f'{p}-{kind}-42.json' for p in ('L2','GA2')]
        if not all(p.exists() for p in paths):continue
        data=[json.loads(p.read_text(encoding='utf-8')) for p in paths];fig=Image.new('RGB',(1560,1050),'#f5f1e8');d=ImageDraw.Draw(fig)
        d.text((25,20),f'EVERREACH | {kind} seed 42 | GA1+L2 x GA1+GA2',font=font(26),fill='#20372d')
        d.text((25,65),f"Populacao real {data[1]['species_id']} | capacidade {data[1]['capacity']} | remocoes {data[1]['removals']}",font=font(19),fill='#20372d')
        for i,day in enumerate((0,7,15,30,60,90,180)):
            y=130+i*114;d.text((25,y),f'Dia {day}',font=font(19),fill='#20372d')
            for j,r in enumerate(data):
                q=r['snapshots'][str(day)]['population'];s=next(p for p in r['snapshots'][str(day)]['structure']['populations'] if p['species_id']==r['species_id'])
                yy=y+j*46;x=155;cap=r['capacity'];survivors=s['surviving_founders'];adults=q['stages']['adult']-survivors
                segments=[(survivors,'#254e36'),(adults,'#549756'),(q['stages']['young'],'#b1c36b'),(q['stages']['germinating'],'#ddd074'),(cap-q['living_count'],'#d4cec3')]
                for n,color in segments:
                    end=x+700*n/cap;d.rectangle((x,yy,end,yy+24),fill=color);x=end
                d.text((100,yy),r['policy'],font=font(14),fill='#20372d')
                text=f"{q['living_count']} vivos | jovens {q['stages']['young']} | adultos novos {adults} | cobertura {s['cover_ppm']/10000:.2f}% | altura {s['mean_height_cm']/100:.2f}m"
                d.text((880,yy),text,font=font(13),fill='#20372d')
        d.text((25,970),'Verde escuro: fundadores | verde: novos adultos | verde claro: jovens | amarelo: germinando | cinza: vagas',font=font(18),fill='#20372d')
        d.text((25,1005),'Cobertura e altura da populacao-alvo, calculadas por VSR1. Nao sao restauracao do teto do patch nem curva idealizada.',font=font(17),fill='#20372d')
        fig.save(out/f'{kind}-comparison.png')


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('../artifacts/vegetation-ga2'))
    p.add_argument('--seeds',type=int,nargs='+',default=[42,0,7,2026,12345]);p.add_argument('--kinds',nargs='+',default=list(KINDS),choices=KINDS)
    p.add_argument('--policies',nargs='+',default=['L2','GA2'],choices=['L2','GA2']);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    records=[run(seed,kind,policy,a.out) for seed in a.seeds for kind in a.kinds for policy in a.policies]
    (a.out/'summary.json').write_text(json.dumps([{k:r[k] for k in ('seed','kind','policy','species_id','first_birth_days','first_maturity_days','body_rows')} for r in records],ensure_ascii=False,indent=2),encoding='utf-8');figures(a.out)


if __name__=='__main__':main()
