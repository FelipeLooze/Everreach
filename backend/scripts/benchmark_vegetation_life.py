"""Copy isolated proof to RAM. Never mutate the proof or a campaign save."""
import json,sqlite3,time,tracemalloc,argparse
from pathlib import Path
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db import models
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_vegetation import GenesisPlantIndividual as Individual
from app.game.time.clock import advance_world_time
from app.game.world.genesis.vegetation import service,lifecycle as life
from app.game.world.genesis.vegetation.life_math import DAY


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('../artifacts/vegetation-life-l1-validated'));a=p.parse_args()
    engine=create_engine('sqlite:///:memory:');event.listen(engine,'connect',enable_sqlite_foreign_keys)
    raw=engine.raw_connection()
    with sqlite3.connect(f'file:{(a.out/"births.sqlite").resolve().as_posix()}?mode=ro',uri=True) as src:src.backup(raw.driver_connection)
    raw.close()
    with Session(engine) as db:
        child=next(r for r in db.query(Individual) if r.baseline.get('origin')=='L1_finite_propagule' and r.state['life']['maturity']!='adult')
        cid=child.campaign_id;start=time.perf_counter();v=service.context(db,cid);cold=time.perf_counter()-start
        advance_world_time(db,cid,365*DAY);start=time.perf_counter();life.sync(db,cid,child,v);persist=time.perf_counter()-start
        state=child.state;sp=v.catalog.species[child.baseline['species_id']];end=life.now(db,cid)+100*365*DAY;tick=time.perf_counter()
        for _ in range(1000):life.project(child.baseline,state,end,sp)
        pure=(time.perf_counter()-tick)*1000/1000
        tracemalloc.start()
        for _ in range(1000):life.project(child.baseline,state,end,sp)
        retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        report={'cold_source_context_seconds':cold,'one_child_365_day_sync_seconds':persist,
            'hundred_year_projection_mean_ms':pure,'projection_repetitions':1000,'traced_retained_bytes':retained,'traced_peak_bytes':peak,
            'materialized_individuals_in_three_proof_campaigns':db.query(Individual).count(),
            'virtual_founders_enumerated':False,'scope':'SQLite_RAM_copy_of_proof; source_loading_excluded_from_traced_projection; HTTP_checkpoint_excluded',
            'proof_database_modified':False,'real_database_accessed':False}
        (a.out/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
    engine.dispose()


if __name__=='__main__':main()
