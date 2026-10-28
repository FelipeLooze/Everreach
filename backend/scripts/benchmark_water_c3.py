"""Matched W1 C2/C3 preparation/recarga costs; never opens a real save."""
import json
from pathlib import Path
import statistics
import time
import tracemalloc
from scripts.validate_water_c3 import inputs,fixed_evidence
from app.game.world.genesis.water.config import WaterConfigC3R155
from app.game.world.genesis.water.plan import build_water_plan,load_water_plan
from app.game.world.genesis.water.query import node_record


def main():
    old,new=inputs(42);regions,_=fixed_evidence(old,42);results={};times={'C2':[],'C3':[]};plans={}
    for round_index in range(3):
        pairs=(('C2',old,None),('C3',new,WaterConfigC3R155()))
        if round_index%2:pairs=tuple(reversed(pairs))
        for label,sampler,config in pairs:
            started=time.perf_counter();plan=build_water_plan(sampler.regional.terrain.plan.source,sampler.h1,sampler.climate,regions,config=config)
            times[label].append(time.perf_counter()-started);plans[label]=plan
    for label,sampler,config in (('C2',old,None),('C3',new,WaterConfigC3R155())):
        tracemalloc.start();measured=build_water_plan(sampler.regional.terrain.plan.source,sampler.h1,sampler.climate,regions,config=config)
        retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop();assert measured==plans[label]
        data=json.dumps(measured.to_dict(),separators=(',',':'));started=time.perf_counter()
        loaded=load_water_plan(json.loads(data),sampler.h1,sampler.climate,measured.hr_signature);loading=time.perf_counter()-started;assert loaded==measured
        queries=[]
        for node in range(128):
            started=time.perf_counter();node_record(measured,node);queries.append((time.perf_counter()-started)*1000)
        results[label]={'build_seconds':times[label],'median_build_seconds':statistics.median(times[label]),'peak_bytes':peak,
            'retained_bytes':retained,'payload_bytes':len(data.encode()),'load_validate_seconds':loading,'median_node_query_ms':statistics.median(queries)}
        print(json.dumps({label:results[label]}),flush=True)
    path=Path('../artifacts/water-c3-compatibility/performance.json')
    path.write_text(json.dumps({'results':results,'scope':'same seed42 and fixed HR1 evidence; excludes physical global authorities; tracemalloc not RSS',
        'caveat':'may overlap regression; memory instrumented separately from timings'},indent=2),encoding='utf-8')


if __name__=='__main__':main()
