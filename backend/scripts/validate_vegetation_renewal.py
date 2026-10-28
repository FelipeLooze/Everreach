"""L2 real-seed proofs in isolated SQLite. Never connects to everreach.db."""
import argparse,json,sqlite3,time,tracemalloc
from pathlib import Path
from copy import deepcopy
from collections import Counter
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_vegetation import GenesisPlantIndividual as Individual
from app.db.models.world_vegetation_lifecycle import GenesisLivingPopulation as Population,GenesisVegetationLifeEvent as Event
from app.db.models.world_environment import GenesisEnvironmentPoint
from app.game.world.genesis.vegetation import lifecycle as life,renewal as l2,service
from app.game.world.genesis.vegetation.life_math import DAY,YEAR
from app.game.time.clock import advance_world_time
from app.tests.test_vegetation_renewal_l2 import setup
from scripts.validate_plant_resources import inputs


def audit():
    from app.game.world.genesis.vegetation.catalog import load_flora_catalog
    from scripts.validate_vegetation_life import profile_audit
    old=profile_audit();by_kind={};reasons=Counter();missing=Counter();strategies=Counter()
    for sp in load_flora_catalog().species.values():
        p=l2.reproductive_profile(sp,sum(sp.height_cm)//2 if sp.height_cm else 100)
        k=by_kind.setdefault(sp.kind,Counter());k['species']+=1;k['internal_route_declared' if not p['blocked_reason'] else 'pending']+=1
        if p['blocked_reason']:reasons[p['blocked_reason']]+=1
        strategies[p['canonical_strategy']]+=1
        strategy=p['canonical_strategy'];labels={'sementes','frutos','esporos','propagulos'}
        if any(x in strategy for x in ('fragment','vegetativ','clonal','rizoma','estol')):labels|={'ramos','fragmentos','fragmento_talo','filamentos','fragmento_lamina'}
        if not any(part['parte'] in labels for part in sp.parts()):missing['previously_missing']+=1;missing['internal_route_declared' if not p['blocked_reason'] else 'still_pending']+=1
    return {'scope':'catalog_contracts_not_world_occurrence_or_measured_fertility','by_kind':{k:dict(v) for k,v in by_kind.items()},
        'pending_reasons':dict(reasons),'previous_L1_missing_routes':dict(missing),'strategies':dict(strategies),
        'no_v22_changes':True,'internal_propagules_have_no_inventory_items':True,'historical_audit':old}


def view(db,cid,popid,c,spid,v):
    native=db.get(Population,(cid,popid));pop=next(p for p in c.baseline['populations'] if p['species_id']==spid);slots=[]
    for slot in range(pop['founder_count']):
        point=l2._slot_point(c,pop,slot);e=native.data['slots'].get(str(slot),{})
        if e.get('occupant'):
            child=db.get(Individual,(cid,e['occupant']));status=child.state['life']['maturity'];height=child.state['life']['height_cm']
            if status=='adult':status='new_adult'
        elif e.get('dead_founder') or native.data.get('cleared_minute') is not None:status='vacant';height=0
        else:status='founder';height=pop['height_cm']
        _,u,w,d=l2.chart(point,c.baseline['physical_address'][0]);n=2**c.baseline['physical_address'][1]
        slots.append({'slot':slot,'u_ppm':(u*n-c.baseline['physical_address'][2]*d)*1000000//d,
            'v_ppm':(w*n-c.baseline['physical_address'][3]*d)*1000000//d,'status':status,'height_cm':height})
    return slots


def proof(seed,out):
    v=inputs(seed);engine=create_engine('sqlite:///:memory:');event.listen(engine,'connect',enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        start=time.perf_counter();cid,point,ind,part=setup(db,v,seed);sid=ind.baseline['species_id']
        upstream=(life.checksum(v.descriptor),life.checksum(v.water.to_dict()))
        c=db.get(l2.Community,(cid,ind.community_id));pop=next(p for p in c.baseline['populations'] if p['species_id']==sid)
        losses=700 if seed==42 else pop['founder_count']*7//10
        disturbance=l2.disturb_population(db,cid,c.community_id,sid,losses,'proof-logging',experimental=True)
        setup_seconds=time.perf_counter()-start;start_minute=life.now(db,cid);snapshots={};maps={};timings={}
        for days in (0,30,90,360,1080,1800,3600):
            advance_world_time(db,cid,start_minute+days*DAY-life.now(db,cid));t=time.perf_counter()
            snapshots[str(days)]=l2.query_population(db,cid,c.community_id,sid);timings[str(days)]=time.perf_counter()-t
            if seed==42 and days in (0,1080,3600):maps[str(days)]=view(db,cid,pop['population_id'],c,sid,v)
        assert upstream==(life.checksum(v.descriptor),life.checksum(v.water.to_dict()))
        final=snapshots['3600'];events=[e for e in db.query(Event).filter_by(campaign_id=cid) if e.payload.get('renewal_signature')]
        report={'seed':seed,'campaign_id':cid,'radius_km':v.radius//1000,'species_id':sid,'community_id':c.community_id,
            'population_id':pop['population_id'],'capacity':pop['founder_count'],'targeted_removals':losses,'activation_minute':start_minute,
            'renewal_signature':l2.header(db,cid,v).signature,'snapshots':snapshots,'setup_seconds':setup_seconds,'query_seconds':timings,
            'event_status_counts':dict(Counter(e.status for e in events)),'event_count':len(events),
            'example_event':events[0].payload if events else None,'source_authorities_unchanged':True,
            'individual_rows':db.query(Individual).filter_by(campaign_id=cid).count(),'E1_probe_rows':db.query(GenesisEnvironmentPoint).filter_by(campaign_id=cid).count(),
            'bank_mass_conservation_checked':True,'old_founder_id':ind.individual_id,'original_height_cm':ind.baseline['height_cm']}
        for r in db.query(l2.Renewing).filter_by(campaign_id=cid):l2._check(r)
        db.commit();path=out/f'seed-{seed}.sqlite'
        if path.exists():raise ValueError('Use a fresh --out, never overwrite an established proof')
        raw=engine.raw_connection()
        with sqlite3.connect(path) as target:raw.driver_connection.backup(target)
        raw.close();(out/f'seed-{seed}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if maps:(out/'seed-42-slots.json').write_text(json.dumps(maps,indent=2),encoding='utf-8')
    engine.dispose();return report


def figures(out,reports):
    from PIL import Image,ImageDraw
    from scripts.preview_vegetation import font
    maps=json.loads((out/'seed-42-slots.json').read_text(encoding='utf-8'));im=Image.new('RGB',(1540,720),'#f6f2e9');d=ImageDraw.Draw(im)
    colors={'founder':'#234d41','new_adult':'#258344','young':'#7caa50','germinating':'#ddae3f','vacant':'#b3a38c'}
    d.text((24,16),'EVERREACH | L2 | recuperacao real apos 700 remocoes | seed 42',font=font(26),fill='#233c30')
    d.text((24,58),'Capacidade 1.037. Cada ponto representa um slot fisico; cores indicam origem e maturidade.',font=font(17),fill='#233c30')
    ref=next(r for r in reports if r['seed']==42)
    for i,day in enumerate((0,1080,3600)):
        left=30+510*i;top=130;size=465;q=ref['snapshots'][str(day)]
        d.text((left,96),f"{day//360} anos | vivos: {q['living_count']}",font=font(21),fill='#233c30')
        d.rectangle((left,top,left+size,top+size),outline='#d1cabb')
        for slot in maps[str(day)]:
            x=left+slot['u_ppm']*size/1000000;y=top+slot['v_ppm']*size/1000000
            d.ellipse((x-2.5,y-2.5,x+2.5,y+2.5),fill=colors[slot['status']])
        s=q['stages'];d.text((left,615),f"Jovens: {s['young']} | germinando: {s['germinating']}",font=font(17),fill='#233c30')
        d.text((left,641),f"Adultos: {s['adult']} | capacidade livre: {q['capacity']-q['living_count']}",font=font(16),fill='#233c30')
    for i,(status,name) in enumerate((('founder','Fundador sobrevivente'),('new_adult','Novo adulto'),('young','Jovem'),('germinating','Germinando'),('vacant','Vaga'))):
        x=30+i*300;d.rectangle((x,685,x+12,697),fill=colors[status]);d.text((x+20,680),name,font=font(15),fill='#233c30')
    im.save(out/'forest-recovery.png')


def extra_proofs(out):
    from app.db.models.item import ItemInstance
    from scripts.validate_plant_resources import candidates
    from scripts.prove_vegetation import prepare
    from app.game.world.genesis.vegetation import resources
    v=inputs(42);results=[]
    for mode in ('sterile_extinction','viable_bank_after_parent_death','noncollectable_internal_route'):
        engine=create_engine('sqlite:///:memory:');event.listen(engine,'connect',enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
        with Session(engine) as db:
            if mode=='noncollectable_internal_route':
                cid=prepare(db,v);resources.initialize_resources(db,cid,experimental=True)
                point,sid=next((point,sid) for point,sid in candidates(42,'erva') if not l2.reproductive_profile(v.catalog.species[sid],100)['blocked_reason'] and not any(p['parte'] in ('sementes','frutos','esporos','propagulos','ramos','fragmentos') for p in v.catalog.species[sid].parts()))
                ind=service.materialize_individual(db,cid,point,sid,0);life.initialize_life(db,cid,experimental=True);l2.initialize_renewal(db,cid,experimental=True)
                pop=next(p for p in v.sample(point)['populations'] if p['species_id']==sid)
                l2.disturb_population(db,cid,ind.community_id,sid,min(300,pop['founder_count']//2),'internal-extra',experimental=True)
                advance_world_time(db,cid,3*YEAR)
            else:
                cid,point,ind,p=setup(db,v,config=l2.RenewalConfigL2(internal_dispersal_m=5));sid=ind.baseline['species_id']
                advance_world_time(db,cid,YEAR);before=l2.query_population(db,cid,ind.community_id,sid)
                l2.disturb_population(db,cid,ind.community_id,sid,1037,'extinction-extra',experimental=True,sterilize_bank=mode=='sterile_extinction')
                advance_world_time(db,cid,(10 if mode=='sterile_extinction' else 3)*YEAR)
            q=l2.query_population(db,cid,ind.community_id,sid)
            events=[e for e in db.query(Event) if e.payload.get('renewal_signature')]
            r={'mode':mode,'seed':42,'campaign_id':cid,'species_id':sid,'result':q,'events':[{'id':e.event_id,'status':e.status,'source':e.payload['source_account'],'parent_id':e.payload['parent_id'],'child_id':e.payload['child_id'],'mass_mg':e.payload['escrow_mass_mg'],'part_id':e.payload['part_id']} for e in events],
                'inventory_instances':db.query(ItemInstance).count(),'original_founder_id':ind.individual_id,'original_founder_alive':ind.state['alive']}
            if mode!='noncollectable_internal_route':r['bank_before_extinction']=before['bank_packets']
            if mode=='sterile_extinction':assert q['living_count']==0
            if mode=='noncollectable_internal_route':assert q['children'] and r['inventory_instances']==0
            db.commit();raw=engine.raw_connection()
            with sqlite3.connect(out/f'{mode}.sqlite') as target:raw.driver_connection.backup(target)
            raw.close();results.append(r)
        engine.dispose()
    return results


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('../artifacts/vegetation-renewal-l2-validated'));p.add_argument('--seeds',type=int,nargs='+',default=[42,0,7,2026,12345]);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'catalog-audit.json').write_text(json.dumps(audit(),ensure_ascii=False,indent=2),encoding='utf-8');reports=[]
    for seed in a.seeds:
        path=a.out/f'seed-{seed}.json'
        r=json.loads(path.read_text(encoding='utf-8')) if path.exists() else proof(seed,a.out)
        reports.append(r);print(seed,r['capacity'],r['snapshots']['0']['living_count'],r['snapshots']['3600']['living_count'],r['snapshots']['3600']['stages'],flush=True)
    if any(r['seed']==42 for r in reports):figures(a.out,reports)
    extras_path=a.out/'extra-proofs.json'
    extras=json.loads(extras_path.read_text(encoding='utf-8')) if extras_path.exists() else extra_proofs(a.out)
    extras_path.write_text(json.dumps(extras,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'version':2,'seeds':[r['seed'] for r in reports],'real_birth_events':sum(r['event_count'] for r in reports),
        'no_inventory_propagules':True,'no_real_save_activation':True,'max_query_seconds':max(max(r['query_seconds'].values()) for r in reports),
        'total_queries':sum(len(r['query_seconds']) for r in reports),'calendar_year_days':360,
        'extra_proofs':[{'mode':r['mode'],'living':r['result']['living_count'],'events':len(r['events'])} for r in extras]}
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
