"""C2/C3 preparation, memory, resolution and radius diagnostics; disposable only."""
import json
from pathlib import Path
import statistics
import time
import tracemalloc
from app.game.world.genesis.climate.plan import build_climate_plan,load_climate_plan
from app.game.world.genesis.climate.geometry import geometry
from app.game.world.genesis.climate.query import sample_climate
from app.game.world.genesis.climate.calibration import report
from app.game.world.genesis.climate.v3 import ClimateConfigV3
from scripts.validate_environment import environment_inputs
from scripts.compare_climate_versions import solve


def run():
    output=Path('../artifacts/climate-recalibration-0.9.1');output.mkdir(parents=True,exist_ok=True)
    old=environment_inputs(42,63710000);source=old.regional.terrain.plan.source
    results={}
    for version,config in ((2,old.climate.config),(3,ClimateConfigV3())):
        times=[]
        for _ in range(3):
            geometry.cache_clear();start=time.perf_counter();plan=build_climate_plan(source,old.h1,config)
            times.append(time.perf_counter()-start)
        tracemalloc.start();measured=build_climate_plan(source,old.h1,config)
        retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        assert measured==plan
        payload=json.dumps(plan.to_dict(),separators=(',',':'));start=time.perf_counter()
        loaded=load_climate_plan(json.loads(payload),source.signature,old.h1.signature,63710000,source.config.sea_level_m)
        load_seconds=time.perf_counter()-start;assert loaded==plan
        queries=[]
        for point in geometry(5).points[:128]:
            start=time.perf_counter();sample_climate(plan,point);queries.append((time.perf_counter()-start)*1000)
        results[str(version)]={'full_build_seconds':times,'median_full_build_seconds':statistics.median(times),
            'peak_bytes':peak,'retained_bytes':retained,'payload_bytes':len(payload.encode()),
            'load_validate_seconds':load_seconds,'median_query_ms':statistics.median(queries)}
        print(json.dumps({'version':version,**results[str(version)]}),flush=True)
    resolution=[]
    for level in (3,4,5):
        for version,config in ((2,old.climate.config.model_copy(update={'level':level})),(3,ClimateConfigV3(level=level))):
            plan=build_climate_plan(source,old.h1,config);r=report(plan)
            resolution.append({'level':level,'version':version,'vertices':len(plan.heights),'land':r['groups']['surface/land'],
                'warning':'native terrain and ocean sampling change; these levels are not interchangeable LOD'})
    radii=[]
    for radius in (6371000,63710000,637100000,10**12):
        baseline=environment_inputs(42,radius).climate
        for plan in (baseline,solve(baseline,ClimateConfigV3())):
            r=report(plan);radii.append({'radius_m':radius,'version':plan.config.climate_version,'signature':plan.signature,
                'moisture_length_m':plan.moisture_length_m,'land':r['groups']['surface/land'],
                'residual_ppm':list(plan.transport_residual_ppm)})
    iteration_checks=[]
    for radius in (6371000,63710000):
        baseline=environment_inputs(42,radius).climate
        for iterations in (64,128):
            plan=solve(baseline,ClimateConfigV3(transport_iterations=iterations))
            iteration_checks.append({'radius_m':radius,'iterations':iterations,
                'land_precipitation_mm':report(plan)['groups']['surface/land']['mean_precipitation_mm'],
                'max_residual_ppm':max(plan.transport_residual_ppm)})
    (output/'performance-sensitivity.json').write_text(json.dumps({'benchmark':results,'resolution':resolution,'radii':radii,'iteration_sensitivity':iteration_checks,
        'scope':'full builds include V4 sampling, exclude preparation of existing V4/H1; tracemalloc not RSS; no ORM',
        'timing_caveat':'may overlap offline validation; instrumented memory measured separately from timings'},indent=2),encoding='utf-8')


if __name__=='__main__':run()
