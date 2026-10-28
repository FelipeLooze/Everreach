import gc,json,time,tracemalloc
from scripts.validate_vegetation import inputs_vg1,centers
from scripts.calibrate_vegetation import OUT
from app.game.world.genesis.vegetation.v2 import VegetationSamplerV2
from app.game.world.genesis.geology.regional.experiment import window_point


def main():
    old=inputs_vg1(42,"exploration_mosaic_v1");new=VegetationSamplerV2(old.environment,old.water)
    center=centers(42)["moderate"];points=[window_point(center,1000*i,5000,old.radius) for i in range(160)]
    results={}
    for label,v in (("Vg1",old),("Vg2",new)):
        start=time.perf_counter()
        for p in points:v.sample(p)
        elapsed=time.perf_counter()-start;start=time.perf_counter();v.sample(points[-1]);cached=time.perf_counter()-start
        results[label]={"new_patch_queries":160,"untraced_seconds":elapsed,"mean_ms":elapsed*1000/160,"cached_ms":cached*1000,
            "patch_cache":len(v.cache),"cohort_cache":len(getattr(v,"cohorts",{}))}
    # Separate bounded run includes new cohort and patch allocation, excluding catalog.
    measured=VegetationSamplerV2(old.environment,old.water);gc.collect();tracemalloc.start()
    for p in points[:64]:measured.sample(p)
    now,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    result={"versions":results,"Vg2_retained_query_bytes":now,"Vg2_peak_query_bytes":peak,"traced_patches":64,
        "sources_and_catalog_excluded_from_traced_allocations":True,"no_global_population_materialization":True}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/"benchmark.json").write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)


if __name__=="__main__":main()
