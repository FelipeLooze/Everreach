"""Bounded import/query measurements, in a fresh process with traced allocations."""
import gc,json,time,tracemalloc
from app.game.world.genesis.vegetation.catalog import load_flora_catalog
from app.game.world.genesis.vegetation.field import VegetationSampler
from app.game.world.genesis.vegetation.config import VegetationConfig
from app.game.world.genesis.geology.regional.experiment import window_point
from app.game.world.genesis.terrain.field import checksum
from scripts.validate_vegetation import inputs_vg1,centers,OUT


def main():
    tracemalloc.start();t=time.perf_counter();catalog=load_flora_catalog();import_seconds=time.perf_counter()-t
    gc.collect();current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    baseline=inputs_vg1(42);directed=VegetationSampler(baseline.environment,baseline.water,VegetationConfig(policy="exploration_mosaic_v1"))
    c=centers(42)["moderate"];points=[window_point(c,1000*i,5000,baseline.radius) for i in range(160)]
    rows={}
    for label,v in (("ecological",baseline),("directed",directed)):
        tracemalloc.start();start=time.perf_counter()
        samples=[v.sample(p) for p in points]
        elapsed=time.perf_counter()-start;now,high=tracemalloc.get_traced_memory();tracemalloc.stop()
        start=time.perf_counter();v.sample(points[-1]);revisit=time.perf_counter()-start
        rows[label]={"distinct_queries":len(samples),"traced_query_seconds":elapsed,"traced_mean_ms":1000*elapsed/len(samples),
            "retained_query_bytes":now,"peak_query_bytes":high,"sampler_cache_entries":len(v.cache),
            "cached_query_seconds":revisit,"worldwide_population_enumeration":False,"individuals_materialized":0,
            "checksum":checksum(samples)}
    report={"catalog_import_seconds_traced":import_seconds,"catalog_retained_bytes":current,"catalog_peak_bytes":peak,
        "catalog_source_bytes":59110915,"profiles":len(catalog.species),"queries":rows,
        "measurement_limit":"tracemalloc overhead; fresh catalog parse includes transient full source tree; queries exclude source preparation"}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/"benchmark.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__=="__main__":main()
