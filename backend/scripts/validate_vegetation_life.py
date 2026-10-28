"""Reproducible isolated L1 proofs; never connects to everreach.db.

Run: python -m scripts.validate_vegetation_life --out ../artifacts/vegetation-life-l1
"""
import argparse,json,time,sqlite3,tracemalloc
from copy import deepcopy
from pathlib import Path
from collections import Counter
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_vegetation import GenesisPlantIndividual as Individual
from app.db.models.world_vegetation_lifecycle import GenesisVegetationLifeEvent as Event
from app.game.world.genesis.vegetation import lifecycle as life,service,resources
from app.game.world.genesis.vegetation.life_math import LifeConfigL1,DAY,life_profile
from app.game.world.genesis.vegetation.catalog import load_flora_catalog
from app.game.time.clock import get_world_time,advance_world_time
from scripts.validate_plant_resources import inputs,actual_individual,prepare_operator,set_window,candidates
from scripts.prove_vegetation import prepare


def find_individual(db,cid,v,seed,kind,rarity=None):
    for point,sid in candidates(seed,kind):
        if rarity and v.catalog.species[sid].rarity_name!=rarity:continue
        for slot in range(8):
            try:ind=service.materialize_individual(db,cid,point,sid,slot)
            except ValueError as exc:
                if 'microsite unsupported' in str(exc):continue
                raise
            for p in v.catalog.species[sid].parts():
                if p['parte'] in life.PARTIAL and ind.state['part_stock'][p['id']]>0:return point,ind,p
    raise ValueError(f'No actual eligible {rarity} {kind}')


def proof(seed,kind,rarity,out):
    t=time.perf_counter();v=inputs(seed);engine=create_engine('sqlite:///:memory:')
    event.listen(engine,'connect',enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid=prepare(db,v);resources.initialize_resources(db,cid,experimental=True)
        if kind=='rare':
            for physical_kind in ('liquen','arbusto','erva','arvore','graminea','flor'):
                try:point,ind,p=find_individual(db,cid,v,seed,physical_kind,rarity)
                except ValueError as exc:
                    if str(exc).startswith('No actual eligible'):continue
                    raise
                break
            else:raise ValueError(f'No actual renewable rare species in reference windows for seed {seed}')
        else:point,ind,p=find_individual(db,cid,v,seed,kind,rarity)
        actor,tool=prepare_operator(db,cid,ind,v);set_window(db,cid,p,ind,v)
        life.initialize_life(db,cid,LifeConfigL1(automatic_colonization=False),experimental=True)
        initial=deepcopy(ind.state);pid=p['id'];sp=v.catalog.species[ind.baseline['species_id']]
        maximum=ind.baseline['resource_profile']['parts'][pid]['per_action_max'];n=0
        # Actual finite inventory transfers, never directly reset a stock.
        receipts=[]
        while ind.state['part_stock'][pid]:
            n+=1;qty=min(maximum,ind.state['part_stock'][pid])
            receipts.append(service.harvest(db,cid,actor.id,ind.individual_id,pid,qty,tool.id,f'deplete-{n}'))
        start=life.now(db,cid);collected=deepcopy(ind.state);snapshots={}
        tick=time.perf_counter()
        for _ in range(100):life.project(ind.baseline,collected,start+365*DAY,sp)
        projection_ms=(time.perf_counter()-tick)*10
        tracemalloc.start()
        for _ in range(100):life.project(ind.baseline,collected,start+365*DAY,sp)
        _,projection_peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        for day in (7,30,90,365):
            advance_world_time(db,cid,start+day*DAY-life.now(db,cid));life.sync(db,cid,ind,v)
            direct=life.project(ind.baseline,collected,start+day*DAY,sp)
            assert direct==ind.state
            snapshots[str(day)]={'minute':life.now(db,cid),'stock':ind.state['part_stock'][pid],
                'height_cm':ind.state['life']['height_cm'],'maturity':ind.state['life']['maturity'],
                'alive':ind.state['alive'],'assimilated_mass_mg':ind.state['life']['assimilated_mass_mg']}
        report={'seed':seed,'scenario':kind,'species_id':sp.id,'kind':sp.kind,'rarity':sp.rarity_name,'part_id':pid,'part':p['parte'],
            'individual_id':ind.individual_id,'baseline_checksum':ind.baseline_checksum,'start_minute':start,
            'recovery_active_days':ind.state['life']['profile']['recovery_days'][pid],
            'rates_ppm':ind.state['life']['rates'],'maximum_stock':ind.baseline['resource_profile']['parts'][pid]['max_units'],
            'initial_stock':initial['part_stock'][pid],'post_collect_stock':collected['part_stock'][pid],
            'snapshots':snapshots,'receipts':receipts,'chunks_equal_direct':True,'seconds':time.perf_counter()-t,
            'projection_mean_ms':projection_ms,'projection_peak_bytes':projection_peak,
            'benchmark_scope':'pure_one_individual_365_day_projection_excludes_sources_HTTP_and_persistence'}
        # Whole-body mortality remains permanent, even after another year.
        service.remove_individual(db,cid,actor.id,ind.individual_id,tool.id,'whole-removal')
        advance_world_time(db,cid,365*DAY);life.sync(db,cid,ind,v)
        assert not ind.state['alive'] and not any(ind.state['part_stock'].values())
        report['removed_after_365_days_alive']=ind.state['alive'];db.commit()
        dbpath=out/f'seed-{seed}-{kind}-{rarity or "any"}.sqlite'
        if dbpath.exists():raise ValueError('Proof path already exists; choose a fresh --out')
        raw=engine.raw_connection()
        with sqlite3.connect(dbpath) as target:raw.driver_connection.backup(target)
        raw.close()
    engine.dispose();return report


def birth_proof(out):
    # The same real seed-bearing and clonal tree setup used in regression tests.
    from app.tests.test_vegetation_lifecycle_l1 import reproduction_setup,recolonization_setup
    v=inputs(42);engine=create_engine('sqlite:///:memory:');event.listen(engine,'connect',enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    reports=[]
    for kind in ('erva','arvore','recolonization'):
        with Session(engine) as db:
            cid,parent,dead,e,point=recolonization_setup(db,v) if kind=='recolonization' else reproduction_setup(db,v,kind)
            advance_world_time(db,cid,e.due_minute-life.now(db,cid));life.sync(db,cid,dead,v)
            child=db.get(Individual,(cid,e.payload['child_id']));start=life.now(db,cid);stages={}
            for day in (0,7,30,90,365):
                advance_world_time(db,cid,start+day*DAY-life.now(db,cid));life.sync(db,cid,child,v)
                stages[str(day)]={'height_cm':child.state['life']['height_cm'],'maturity':child.state['life']['maturity'],
                    'stock':child.state['part_stock'],'mass_mg':sum(child.state['tissue_remaining_mg'].values()),'assimilated_mass_mg':child.state['life']['assimilated_mass_mg']}
            c=service.query_community(db,cid,point);pop=next(p for p in c['populations'] if p['species_id']==parent.baseline['species_id'])
            assert pop['living_count']==(1 if kind=='recolonization' else pop['founder_count'])
            reports.append({'campaign_id':cid,'kind':kind,'parent_id':parent.individual_id,'dead_id':dead.individual_id,'child_id':child.individual_id,
                'event_id':e.event_id,'event_payload':e.payload,'due_minute':e.due_minute,'status':e.status,
                'population_capacity':pop['founder_count'],'living_count':pop['living_count'],
                'mature_active_days':child.state['life']['profile']['mature_active_days'],'stages':stages})
            db.commit()
    path=out/'births.sqlite'
    if path.exists():raise ValueError('Choose fresh --out')
    raw=engine.raw_connection()
    with sqlite3.connect(path) as target:raw.driver_connection.backup(target)
    raw.close();engine.dispose();return reports


def figures(out,data,births):
    # Same lightweight raster stack as the existing technical vegetation previews.
    from PIL import Image,ImageDraw
    from scripts.preview_vegetation import font
    im=Image.new('RGB',(1440,840),'#f6f2e9');d=ImageDraw.Draw(im)
    colors=['#1f7450','#4066aa','#a84e3d','#7755a4','#b47915','#23878f','#945267','#577d29','#495f77','#ae6727']
    d.text((35,20),'EVERREACH | L1 experimental | recursos, nascimento e crescimento',font=font(27),fill='#203e30')
    d.text((35,65),'Cinco seeds reais, raio 63.710 km. Sem alterar clima, agua ou a distribuicao Vg2.',font=font(19),fill='#27382f')
    def axes(left,title,xmax,xticks,subtitle):
        top=160;width=570;height=325
        d.text((left,115),title,font=font(21),fill='#203e30')
        for value in (0,25,50,75,100):
            y=top+height-value*height/100;d.line((left,y,left+width,y),fill='#d3d5ca')
            d.text((left-31,y-9),str(value),font=font(13),fill='black')
        d.line((left,top,left,top+height,left+width,top+height),fill='#243d2f',width=2)
        for x in xticks:d.text((left+x*width/xmax-6,top+height+9),str(x),font=font(14),fill='black')
        d.text((left,top+height+38),subtitle,font=font(16),fill='#243d2f')
        return lambda x,y:(left+x*width/xmax,top+height-y*height/100)
    a=axes(75,'Estoque recuperado: % do teto finito R1',30,(0,7,14,21,30),'Dias desde a coleta integral do estoque renovavel')
    b=axes(800,'Novo individuo: % da altura adulta',365,(0,90,180,270,365),'Dias desde o estabelecimento de um propagulo finito')
    def series(points,color):
        d.line(points,fill=color,width=3)
        for x,y in points:d.ellipse((x-4,y-4,x+4,y+4),fill=color)
    for i,r in enumerate(data):
        series([a(0,0)]+[a(day,r['snapshots'][str(day)]['stock']/r['maximum_stock']*100) for day in (7,30)],colors[i])
        y=565+i*23;d.line((75,y+8,96,y+8),fill=colors[i],width=4)
        d.text((105,y),f"seed {r['seed']} | {r['species_id']} | {r['rarity']} | {r['recovery_active_days']} dias ativos",font=font(14),fill='#243d2f')
    for i,r in enumerate(births):
        cap=r['event_payload']['target_baseline']['height_cm'];color=colors[i+1]
        series([b(day,r['stages'][str(day)]['height_cm']/cap*100) for day in (0,7,30,90,365)],color)
        y=565+i*48;d.line((800,y+8,822,y+8),fill=color,width=4)
        d.text((832,y),f"{r['kind']} | maturidade: {r['mature_active_days']} dias ativos",font=font(16),fill='#243d2f')
        d.text((832,y+22),f"365 d: {r['stages']['365']['maturity']} | {r['stages']['365']['height_cm']} cm",font=font(14),fill='#243d2f')
    d.text((800,745),'Pontos = estados persistidos; segmentos ligam amostras.',font=font(15),fill='#243d2f')
    d.text((800,771),'Arvore adulta recuperada e arvore jovem sao casos distintos.',font=font(15),fill='#243d2f')
    im.save(out/'recovery-and-growth.png')


def profile_audit():
    kinds={};mortality=Counter()
    for sp in load_flora_catalog().species.values():
        profile=life_profile(sp);strategy=str(profile['propagation_strategy']).lower()
        labels={'sementes','frutos','propagulos','esporos'}
        if any(s in strategy for s in ('fragment','vegetativ','clonal','rizoma','estol')):labels|={'ramos','fragmentos','fragmento_talo','filamentos','fragmento_lamina'}
        source=any(p['parte'] in labels for p in sp.parts());k=kinds.setdefault(sp.kind,Counter())
        k['catalog_species']+=1;k['raw_propagule_route_present' if source else 'no_calibrated_raw_propagule_route']+=1
        k['exceptional_blocked']+=int(sp.magic=='excepcional')
        for p in sp.parts():
            if p.get('colheita_preserva_individuo') is False:
                mortality['historical_false_parts']+=1
                mortality['L1_partial_interpretation' if p['parte'] in life.PARTIAL else 'L1_conservative_fatal']+=1
    return {'scope':'catalog_anatomical_contracts_not_world_occurrences_or_authorization',
        'by_kind':{k:dict(v) for k,v in kinds.items()},'mortality_flags':dict(mortality),
        'pending_contract':'noncollectable_propagule_mass_not_invented_for_leaf_bark_only_species'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('../artifacts/vegetation-life-l1-validated'));a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();report_path=a.out/'recovery.json'
    reports=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else []
    for r in reports:
        if 'scenario' not in r:r['scenario']='rare' if r['rarity']=='raro' else r['kind']
    for seed in (42,0,7,2026,12345):
        for kind,rarity in (('arvore',None),('rare','raro')):
            if any(r['seed']==seed and r['scenario']==kind for r in reports):continue
            r=proof(seed,kind,rarity,a.out);reports.append(r)
            (a.out/'recovery.json').write_text(json.dumps(reports,indent=2,ensure_ascii=False),encoding='utf-8')
            print(seed,kind,r['species_id'],{d:s['stock'] for d,s in r['snapshots'].items()},flush=True)
    birth_path=a.out/'births.json'
    births=json.loads(birth_path.read_text(encoding='utf-8')) if birth_path.exists() else birth_proof(a.out)
    birth_path.write_text(json.dumps(births,ensure_ascii=False,indent=2),encoding='utf-8')
    (a.out/'profile-audit.json').write_text(json.dumps(profile_audit(),indent=2,ensure_ascii=False),encoding='utf-8')
    profiles=[life_profile(s) for s in load_flora_catalog().species.values()]
    report={'version':'L1','seeds':[42,0,7,2026,12345],'reference_radius_km':63710,'real_recovery_proofs':len(reports),'births':len(births),
        'rarity_profiles':dict(Counter(p['rarity'] for p in profiles)),'exceptional_materialized':0,'latest_run_seconds':time.perf_counter()-start,
        'recovery_proof_seconds_sum':sum(r['seconds'] for r in reports),
        'projection_peak_bytes_max':max(r['projection_peak_bytes'] for r in reports),'projection_mean_ms_max':max(r['projection_mean_ms'] for r in reports),
        'mass_policy':'finite_R1_pools_and_explicit_modeled_assimilation','no_water_stock_debits':True,'no_real_save_activation':True}
    (a.out/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8');figures(a.out,reports,births)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
