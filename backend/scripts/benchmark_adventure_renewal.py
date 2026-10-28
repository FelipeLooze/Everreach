"""Independent jumps from the same actual disturbed snapshot; includes queries."""
import argparse,json,sqlite3,time
from pathlib import Path
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.database import enable_sqlite_foreign_keys
from app.game.time.clock import advance_world_time
from app.game.world.genesis.vegetation import renewal as l2,service
from app.game.world.genesis.vegetation.life_math import DAY
from app.game.world.genesis.vegetation.recovery_structure import measure_community


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('../artifacts/vegetation-ga2'))
    p.add_argument('--days',type=int,nargs='+',default=[30,60,90,180,360,1800,3600]);p.add_argument('--policies',nargs='+',default=['L2','GA2']);a=p.parse_args()
    dest=a.out/'benchmark.json';records=json.loads(dest.read_text()) if dest.exists() else []
    for policy in a.policies:
        report=json.loads((a.out/f'{policy}-large_tree-42.json').read_text(encoding='utf-8'));cid=report['campaign_id']
        for days in a.days:
            if any(r['policy']==policy and r['days']==days for r in records):continue
            e=create_engine('sqlite:///:memory:');event.listen(e,'connect',enable_sqlite_foreign_keys);raw=e.raw_connection()
            with sqlite3.connect((a.out/f'{policy}-large_tree-42-initial.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as src:src.backup(raw.driver_connection)
            raw.close()
            with Session(e) as db:
                t=time.perf_counter();v=service.context(db,cid);cold=time.perf_counter()-t
                advance_world_time(db,cid,days*DAY);t=time.perf_counter()
                q=l2.query_population(db,cid,report['community_id'],report['species_id']);update=time.perf_counter()-t
                t=time.perf_counter();s=measure_community(db,cid,report['community_id'],v=v,advance=False);structure=time.perf_counter()-t
                t=time.perf_counter();again=l2.query_population(db,cid,report['community_id'],report['species_id']);revisit=time.perf_counter()-t;assert q==again
                r={'policy':policy,'days':days,'cold_context_seconds':cold,'ecology_query_seconds':update,'structure_seconds':structure,
                   'same_time_revisit_seconds':revisit,'living':q['living_count'],'stages':q['stages'],
                   'event_rows':db.query(l2.Event).filter_by(campaign_id=cid).count(),
                   'body_rows':db.query(l2.Individual).filter_by(campaign_id=cid).count(),'revisit_equal':True,
                   'stats':db.info.get(('GA2_last_stats',cid))}
                records.append(r);dest.write_text(json.dumps(records,indent=2),encoding='utf-8');print(policy,days,round(update,3),q['living_count'],flush=True)
            e.dispose()


if __name__=='__main__':main()
