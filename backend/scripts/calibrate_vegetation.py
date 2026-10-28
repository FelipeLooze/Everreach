"""Phase 1.0.1: same geography, frozen Vg1 controls, new independent Vg2 authority."""
from collections import Counter
import argparse,gc,json,time
from pathlib import Path
from scripts.validate_vegetation import inputs_vg1,centers,SCALES,ROOT,summarize
from app.game.world.genesis.vegetation.v2 import VegetationSamplerV2
from app.game.world.genesis.vegetation.config import VegetationConfigV2,VegetationConfig
from app.game.world.genesis.vegetation.field import VegetationSampler
from app.game.world.genesis.vegetation.diagnostics import route_diagnostics,components,structure
from app.game.world.genesis.geology.regional.experiment import window_point
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.sphere_topology import SurfacePoint

OUT=ROOT/"artifacts/vegetation-1.0.1"


def run(seed):
    start=time.perf_counter();old=inputs_vg1(seed,"exploration_mosaic_v1");new=VegetationSamplerV2(old.environment,old.water)
    old_root=ROOT/f"artifacts/vegetation-vg1/seed-{seed}"
    before=checksum(old.environment.climate.to_dict()),checksum(old.water.to_dict())
    windows={};routes={};all_samples={};cold_start=time.perf_counter()-start;start=time.perf_counter()
    for name,center in centers(seed).items():
        routes[name]={}
        for km in SCALES:
            points=[window_point(center,km*1000*(i-10)//20,0,new.radius) for i in range(21)]
            samples={label:[v.sample(p) for p in points] for label,v in (("Vg1",old),("Vg2",new))}
            routes[name][str(km)]={label:route_diagnostics(ss,km*1000) for label,ss in samples.items()}
            routes[name][str(km)]["samples"]={label:[{"community_id":s["community_id"],"dominant_species":s["dominant_species"],**structure(s)} for s in ss] for label,ss in samples.items()}
            for s in samples["Vg2"]:all_samples[s["community_id"]]=s
        # Exactly the same grid and coordinates as the frozen Vg1 visualization.
        old_window=json.loads((old_root/"exploration_mosaic_v1/windows.json").read_text(encoding="utf-8"))[name]
        controls=json.loads((old_root/"ecological_v1/windows.json").read_text(encoding="utf-8"))[name]
        grid=[[new.sample(SurfacePoint(*s["point"])) for s in row] for row in old_window["grid"]]
        # A selected control is regenerated to catch accidental Vg1 changes.
        assert old.sample(SurfacePoint(*old_window["grid"][0][0]["point"]))==old_window["grid"][0][0]
        windows[name]={"width_km":20,"Vg1":old_window["grid"],"Vg2":grid,
            "metrics":{label:{**summarize([s for row in g for s in row]),"structure_components":components(g,"physiognomy"),
                "dominant_components":components(g,"dominant_species")} for label,g in (("ecological_v1",controls["grid"]),("Vg1",old_window["grid"]),("Vg2",grid))}}
        for row in grid:
            for s in row:all_samples[s["community_id"]]=s
    # Larger scale makes regional continuity visible, independent of per-species colors.
    wide={}
    for name in ("wet","moderate","arid"):
        c=centers(seed)[name];points=[[window_point(c,(2*x+1-16)*100000//32,(16-2*y-1)*100000//32,new.radius) for x in range(16)] for y in range(16)]
        wide[name]={label:[[v.sample(p) for p in row] for row in points] for label,v in (("Vg1",old),("Vg2",new))}
        for row in wide[name]["Vg2"]:
            for s in row:all_samples[s["community_id"]]=s
    elapsed=time.perf_counter()-start
    assert before==(checksum(old.environment.climate.to_dict()),checksum(old.water.to_dict()))
    report={"seed":seed,"radius_m":new.radius,"config":new.config.model_dump(mode="json"),"signature":new.signature,
        "source_preparation_seconds":cold_start,"paired_query_seconds":elapsed,**summarize(list(all_samples.values())),
        "windows":{k:v["metrics"] for k,v in windows.items()},"routes":{name:{km:{k:v for k,v in row.items() if k!="samples"} for km,row in scales.items()} for name,scales in routes.items()},
        "patch_cache":len(new.cache),"cohort_cache":len(new.cohorts),"physical_authorities_unchanged":True,
        "old_authority_unchanged":True,"mass_or_yield_calibrations_approved":0}
    folder=OUT/f"seed-{seed}";folder.mkdir(parents=True,exist_ok=True)
    for name,data in (("authority",new.descriptor),("report",report),("windows",windows),("routes",routes),("wide-windows",wide),("communities",all_samples)):
        (folder/f"{name}.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("seed","species_established","physiognomies","paired_query_seconds")}),flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--seeds",type=int,nargs="+",default=[42,0,7,2026,12345]);args=parser.parse_args()
    results=[]
    for seed in args.seeds:results.append(run(seed));gc.collect()
    OUT.mkdir(parents=True,exist_ok=True);(OUT/"comparison.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
