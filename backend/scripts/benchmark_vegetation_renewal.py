"""Bounded L2 catch-up profile using a RAM copy of an isolated real proof."""
import argparse,json,sqlite3,time,cProfile,pstats,io,ctypes
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import models
from app.db.models.world_vegetation_renewal import GenesisVegetationRenewal as Plan,GenesisRenewingPopulation as Population
from app.db.models.world_vegetation import GenesisPlantIndividual as Individual
from app.db.models.world_vegetation_lifecycle import GenesisVegetationLifeEvent as Event
from app.game.time.clock import advance_world_time
from app.game.world.genesis.vegetation import renewal as l2,service
from app.game.world.genesis.vegetation.life_math import YEAR


def memory():
    try:
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(k,ctypes.c_size_t) for k in ('peak_rss','rss','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
        c=Counters();c.cb=ctypes.sizeof(c)
        handle=ctypes.windll.kernel32.GetCurrentProcess
        handle.restype=wintypes.HANDLE
        info=ctypes.windll.psapi.GetProcessMemoryInfo
        info.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD];info.restype=wintypes.BOOL
        if not info(handle(),ctypes.byref(c),c.cb):return None
        return {'working_set_bytes':c.rss,'peak_working_set_bytes':c.peak_rss}
    except (AttributeError,OSError):return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('../artifacts/vegetation-renewal-l2-validated'));parser.add_argument('--seed',type=int,default=42);a=parser.parse_args()
    proof=json.loads((a.out/f'seed-{a.seed}.json').read_text(encoding='utf-8'));engine=create_engine('sqlite:///:memory:');raw=engine.raw_connection()
    with sqlite3.connect('file:'+(a.out/f'seed-{a.seed}.sqlite').resolve().as_posix()+'?mode=ro',uri=True) as src:src.backup(raw.driver_connection)
    raw.close()
    with Session(engine) as db:
        cid=proof['campaign_id'];start=time.perf_counter();v=service.context(db,cid);cold=time.perf_counter()-start
        before=memory();advance_world_time(db,cid,YEAR);start=time.perf_counter();q=l2.query_population(db,cid,proof['community_id'],proof['species_id']);catchup=time.perf_counter()-start;after=memory()
        sizes=[len(json.dumps(r.data,separators=(',',':')).encode()) for r in db.query(Population).filter_by(campaign_id=cid)]
        advance_world_time(db,cid,YEAR);profile=cProfile.Profile();profile.enable();l2.query_population(db,cid,proof['community_id'],proof['species_id']);profile.disable()
        stream=io.StringIO();pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(35)
        (a.out/'profile.txt').write_text(stream.getvalue(),encoding='utf-8')
        report={'seed':a.seed,'source_year':10,'catchup_years':1,'unprofiled_catchup_seconds':catchup,'cold_source_context_seconds':cold,
            'tracked_populations':len(sizes),'renewal_state_json_bytes':sum(sizes),'max_population_json_bytes':max(sizes),
            'individual_rows':db.query(Individual).filter_by(campaign_id=cid).count(),'events':db.query(Event).filter_by(campaign_id=cid).count(),
            'target_capacity':q['capacity'],'living_after_unprofiled_catchup':q['living_count'],'memory_before':before,'memory_after':after,
            'scope':'whole_process_including_existing_geography_catalog_and_RAM_database; CPU profile measures a separate following year',
            'proof_database_modified':False,'real_database_accessed':False,'no_background_ecological_worker':True}
        (a.out/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
    engine.dispose()


if __name__=='__main__':main()
