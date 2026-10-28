"""Whole-process memory around the largest twenty-year controlled catch-up."""
import json,sqlite3,time
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import models
from app.game.world.genesis.vegetation import renewal as l2
from app.game.world.genesis.vegetation.life_math import YEAR
from app.game.time.clock import advance_world_time
from scripts.benchmark_vegetation_renewal import memory


def main():
    out=Path('../artifacts/vegetation-stabilization-1.1.2');meta=json.loads((out/'initial-12345.json').read_text());cid=meta['campaign_id']
    engine=create_engine('sqlite:///:memory:');raw=engine.raw_connection()
    with sqlite3.connect('file:'+(out/'initial-12345.sqlite').resolve().as_posix()+'?mode=ro',uri=True) as src:src.backup(raw.driver_connection)
    raw.close()
    with Session(engine) as db:
        start=time.perf_counter();v=l2.service.context(db,cid);cold=time.perf_counter()-start;before=memory()
        advance_world_time(db,cid,20*YEAR);start=time.perf_counter();q=l2.query_population(db,cid,meta['community_id'],meta['species_id']);elapsed=time.perf_counter()-start;after=memory()
        record={'seed':12345,'years':20,'cold_context_seconds':cold,'ecology_and_query_seconds':elapsed,'memory_before':before,'memory_after':after,
            'living':q['living_count'],'new_individuals':len(q['children']),'batch_stats':db.info.get(('L2_last_batch_stats',cid)),
            'scope':'whole_process_with_existing_world_plans_catalog_and_RAM_SQLite; not_isolated_L2_heap','real_campaign_modified':False}
        (out/'memory-benchmark.json').write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record),flush=True)
    engine.dispose()


if __name__=='__main__':main()
