"""Same initial SQLite snapshot, same L2 rules, independent temporal horizons."""
import argparse,json,sqlite3,time
from pathlib import Path
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_vegetation import GenesisPlantIndividual as Individual
from app.db.models.world_vegetation_lifecycle import GenesisLivingPopulation as Native,GenesisVegetationLifeEvent as Event
from app.game.world.genesis.vegetation import renewal as l2,lifecycle as life
from app.game.world.genesis.vegetation.life_math import YEAR
from app.game.time.clock import advance_world_time
from app.tests.test_vegetation_renewal_l2 import setup
from scripts.validate_plant_resources import inputs


def digest(db,cid):
    from app.db.models.world_vegetation_renewal import GenesisRenewingPopulation as Pop
    data={}
    for model,key,fields in ((Pop,'population_id',('data',)),(Native,'population_id',('data',)),
        (Individual,'individual_id',('baseline','state')),(Event,'event_id',('status','payload','due_minute'))):
        data[model.__tablename__]={getattr(r,key):[getattr(r,f) for f in fields] for r in db.query(model).filter_by(campaign_id=cid)}
    return life.checksum(data)


def initial(seed,out):
    path=out/f'initial-{seed}.sqlite'
    if path.exists():return json.loads((out/f'initial-{seed}.json').read_text(encoding='utf-8'))
    v=inputs(seed);engine=create_engine('sqlite:///:memory:');event.listen(engine,'connect',enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid,q,ind,p=setup(db,v,seed);c=db.get(l2.Community,(cid,ind.community_id));pop=next(x for x in c.baseline['populations'] if x['species_id']==ind.baseline['species_id'])
        n=700 if seed==42 else pop['founder_count']*7//10
        l2.disturb_population(db,cid,ind.community_id,ind.baseline['species_id'],n,'proof-logging',experimental=True);db.commit()
        meta={'seed':seed,'campaign_id':cid,'community_id':ind.community_id,'species_id':ind.baseline['species_id'],'capacity':pop['founder_count'],'removals':n,'signature':l2.header(db,cid,v).signature}
        raw=engine.raw_connection()
        with sqlite3.connect(path) as target:raw.driver_connection.backup(target)
        raw.close();(out/f'initial-{seed}.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    engine.dispose();return meta


def run(seed,years,mode,out):
    meta=initial(seed,out);engine=create_engine('sqlite:///:memory:');raw=engine.raw_connection()
    with sqlite3.connect('file:'+(out/f'initial-{seed}.sqlite').resolve().as_posix()+'?mode=ro',uri=True) as source:source.backup(raw.driver_connection)
    raw.close()
    with Session(engine) as db:
        cid=meta['campaign_id'];db.info[('L2_reference',cid)]=mode=='reference'
        # Context loading is separately measured, then the entire advance and read.
        start=time.perf_counter();v=l2.service.context(db,cid);cold=time.perf_counter()-start
        advance_world_time(db,cid,years*YEAR);start=time.perf_counter();cpu=time.process_time()
        q=l2.query_population(db,cid,meta['community_id'],meta['species_id']);elapsed=time.perf_counter()-start
        result={'seed':seed,'years':years,'engine':mode,'cold_context_seconds':cold,'update_and_query_seconds':elapsed,'update_and_query_cpu_seconds':time.process_time()-cpu,
            'authoritative_digest':digest(db,cid),'signature':meta['signature'],'living':q['living_count'],'stages':q['stages'],'children':len(q['children'])}
        result['batch_stats']=db.info.get(('L2_last_batch_stats',cid))
        # Structure diagnostics do not enter the timed ecology/read interval.
        try:
            from app.game.world.genesis.vegetation.recovery_structure import measure_community
            start=time.perf_counter();result['structure']=measure_community(db,cid,meta['community_id'],v=v,advance=False)
            result['structure_seconds']=time.perf_counter()-start
            result['total_update_query_and_structure_seconds']=elapsed+result['structure_seconds']
        except ImportError:pass
    engine.dispose();return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('../artifacts/vegetation-stabilization-1.1.2'));p.add_argument('--mode',choices=['reference','fast'],required=True);p.add_argument('--seeds',nargs='+',type=int,default=[42,12345]);p.add_argument('--years',nargs='+',type=int,default=[1,5,10,20]);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    rows=[];report=a.out/f'{a.mode}-performance.json'
    if report.exists():rows=json.loads(report.read_text(encoding='utf-8'))
    for seed in a.seeds:
        initial(seed,a.out)
        for years in a.years:
            if any(r['seed']==seed and r['years']==years for r in rows):continue
            r=run(seed,years,a.mode,a.out);rows.append(r);report.write_text(json.dumps(rows,indent=2),encoding='utf-8')
            print(json.dumps({k:r[k] for k in ('seed','years','engine','update_and_query_seconds','authoritative_digest','living','stages')}),flush=True)


if __name__=='__main__':main()
