"""Bounded, offline cost comparison for legacy C3 and explicit R1 profiles."""
import json
from pathlib import Path
import statistics
import time
import tracemalloc
from app.game.world.genesis.climate.v3 import ClimateConfigV3,ClimateConfigV3R1,fraction_optical_depth
from app.game.world.genesis.climate.geometry import geometry
from app.game.world.genesis.climate.plan import build_climate_plan,load_climate_plan
from app.game.world.genesis.climate.query import sample_climate
from scripts.validate_environment import environment_inputs


def run():
    source=environment_inputs(42,63710000);results={}
    for name,config in (('C3-45',ClimateConfigV3()),('R1-45',ClimateConfigV3R1()),('R1-55',ClimateConfigV3R1(land_recycling_ppm=550000))):
        times=[]
        for _ in range(3):
            geometry.cache_clear();fraction_optical_depth.cache_clear();started=time.perf_counter()
            plan=build_climate_plan(source.regional.terrain.plan.source,source.h1,config);times.append(time.perf_counter()-started)
        fraction_optical_depth.cache_clear();tracemalloc.start()
        measured=build_climate_plan(source.regional.terrain.plan.source,source.h1,config)
        retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop();assert measured==plan
        data=json.dumps(plan.to_dict(),separators=(',',':'));started=time.perf_counter()
        loaded=load_climate_plan(json.loads(data),plan.source_signature,plan.hydrology_signature,plan.radius_m,plan.sea_level_m)
        loading=time.perf_counter()-started;assert loaded==plan
        queries=[]
        for p in geometry(5).points[:128]:
            started=time.perf_counter();sample_climate(plan,p);queries.append((time.perf_counter()-started)*1000)
        results[name]={'full_build_seconds':times,'median_build_seconds':statistics.median(times),'peak_bytes':peak,'retained_bytes':retained,
            'payload_bytes':len(data.encode()),'load_seconds':loading,'median_query_ms':statistics.median(queries),
            'log_cache_maxsize':fraction_optical_depth.cache_info().maxsize}
        print(json.dumps({name:results[name]}),flush=True)
    p=Path('../artifacts/climate-c3-final/performance.json');p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(json.dumps({'results':results,'scope':'cold full V4 resampling + climate; preexisting V4/H1 preparation excluded; memory with warm geometry, cold log cache; not RSS',
        'caveat':'may overlap offline validation; timings are indicative'},indent=2),encoding='utf-8')


if __name__=='__main__':run()
