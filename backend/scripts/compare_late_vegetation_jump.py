"""Reproduce the earlier expensive 5->10 year catch-up with identical state."""
import json,sqlite3,time
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import models
from app.game.time.clock import advance_world_time
from app.game.world.genesis.vegetation import renewal as l2
from app.game.world.genesis.vegetation.life_math import YEAR
from scripts.stabilize_vegetation import digest


def main():
    out=Path('../artifacts/vegetation-stabilization-1.1.2');meta=json.loads((out/'initial-12345.json').read_text());cid=meta['campaign_id']
    origin=create_engine('sqlite:///:memory:');raw=origin.raw_connection()
    with sqlite3.connect('file:'+(out/'initial-12345.sqlite').resolve().as_posix()+'?mode=ro',uri=True) as src:src.backup(raw.driver_connection)
    raw.close()
    with Session(origin) as db:
        db.info[('L2_reference',cid)]=True;advance_world_time(db,cid,5*YEAR);t=time.perf_counter();l2.query_population(db,cid,meta['community_id'],meta['species_id']);preparation=time.perf_counter()-t;db.commit()
    results=[]
    for mode in ('reference','fast'):
        engine=create_engine('sqlite:///:memory:');target=engine.raw_connection();source=origin.raw_connection();source.driver_connection.backup(target.driver_connection);source.close();target.close()
        with Session(engine) as db:
            db.info[('L2_reference',cid)]=mode=='reference';v=l2.service.context(db,cid)
            advance_world_time(db,cid,5*YEAR);t=time.perf_counter();q=l2.query_population(db,cid,meta['community_id'],meta['species_id']);seconds=time.perf_counter()-t
            results.append({'engine':mode,'start_year':5,'advance_years':5,'seconds':seconds,'living':q['living_count'],'stages':q['stages'],'digest':digest(db,cid)})
        engine.dispose()
    assert results[0]['digest']==results[1]['digest']
    record={'seed':12345,'preparation_to_start_snapshot_seconds':preparation,'comparison':results,'authoritative_states_equal':True,'speedup':results[0]['seconds']/results[1]['seconds']}
    (out/'late-jump-comparison.json').write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record),flush=True);origin.dispose()


if __name__=='__main__':main()
