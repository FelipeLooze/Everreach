"""Reproducible offline Vg1 experiment; only frozen C3 R1-55 and W1 sources.

Writes actual finite founding-community snapshots, not E1 eligibility maps.
No database used unless --proof explicitly requests a disposable SQLite file.
"""
import argparse
from collections import Counter
import gc,json,time,tracemalloc
from pathlib import Path
from scripts.validate_water_c3 import inputs
from app.game.world.genesis.water.plan import load_water_plan
from app.game.world.genesis.vegetation.field import VegetationSampler
from app.game.world.genesis.vegetation.config import VegetationConfig
from app.game.world.genesis.sphere_topology import SurfacePoint,CellKey,cell_center
from app.game.world.genesis.sphere_area import cell_solid_angle
from app.game.world.genesis.geology.regional.experiment import window_point
from app.game.world.genesis.terrain.field import checksum

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"artifacts/vegetation-vg1"
SCALES=(5,20,50,100,500)


def inputs_vg1(seed,policy="ecological_v1"):
    _,e=inputs(seed)
    data=json.loads((ROOT/f"artifacts/water-c3-compatibility/seed-{seed}/C3-water-plan.json").read_text())
    w=load_water_plan(data,e.h1,e.climate,data["hr_signature"])
    return VegetationSampler(e,w,VegetationConfig(policy=policy))


def centers(seed):
    samples=json.loads((ROOT/f"artifacts/climate-c3-final/seed-{seed}/R1-55-samples.json").read_text())
    land=[p for p in samples if p["land"] and not p["reference_ocean"]]
    # Physical climate ordering only, including problematic dry and cold terrain.
    warm=[p for p in land if 5<p["temperature_c"]<30 and p["P_over_PET"] is not None]
    chosen={"wet":max(warm,key=lambda p:p["P_over_PET"]),
        "dry":min(land,key=lambda p:(p["P_over_PET"] if p["P_over_PET"] is not None else 100,p["rain_mm"])),
        "cold":min(land,key=lambda p:p["temperature_c"]),
        "moderate":min(warm,key=lambda p:abs(p["P_over_PET"]-0.55)),
        "arid":min(warm,key=lambda p:abs(p["P_over_PET"]-0.12))}
    return {k:SurfacePoint(*v["point"]) for k,v in chosen.items()}


def summarize(samples):
    n=len(samples) or 1
    return {"samples":len(samples),"communities":len({s["community_id"] for s in samples}),
        "established_patches":len({s["community_id"] for s in samples if s["established"]}),
        "species_established":len({p["species_id"] for s in samples for p in s["populations"]}),
        "dominant_species":len({s["dominant_species"] for s in samples if s["dominant_species"]}),
        "physiognomies":dict(Counter(s["physiognomy"] for s in samples)),
        "cover_ppm_range":[min((s["cover_ppm"] for s in samples),default=0),max((s["cover_ppm"] for s in samples),default=0)],
        "mean_cover_ppm":sum(s["cover_ppm"] for s in samples)//n,
        "density_per_ha_range":[min((s["density_per_ha"] for s in samples),default=0),max((s["density_per_ha"] for s in samples),default=0)],
        "exceptional_populations":0,"individuals_materialized":0}


def route_metrics(samples,width_m):
    n=max(1,len(samples)-1);keys=[s["dominant_species"] for s in samples]
    longest=run=0
    for i in range(n):
        run=run+1 if keys[i]==keys[i+1] else 0;longest=max(longest,run)
    return {**summarize(samples),"length_km":width_m/1000,"sampling_step_m":width_m//n,
        "dominance_changes":sum(a!=b for a,b in zip(keys,keys[1:])),
        "longest_sampled_unchanged_dominance_km":longest*width_m/n/1000,
        "limit":"sampled_bound_only_not_proof_between_samples"}


def run(seed,policy,*,quick=False):
    start=time.perf_counter();sampler=inputs_vg1(seed,policy);prep=time.perf_counter()-start
    folder=OUT/f"seed-{seed}"/policy;folder.mkdir(parents=True,exist_ok=True)
    all_samples={};routes={};windows={};start=time.perf_counter()
    regions=centers(seed)
    for name,center in regions.items():
        routes[name]={}
        for km in SCALES:
            samples=[sampler.sample(window_point(center,km*1000*(i-10)//20,0,sampler.radius)) for i in range(21)]
            routes[name][str(km)]=route_metrics(samples,km*1000)
            for s in samples:all_samples[s["community_id"]]=s
        size=8 if quick else 16;km=20
        grid=[[sampler.sample(window_point(center,(2*x+1-size)*km*1000//(2*size),
            (size-2*y-1)*km*1000//(2*size),sampler.radius)) for x in range(size)] for y in range(size)]
        for row in grid:
            for s in row:all_samples[s["community_id"]]=s
        windows[name]={"width_km":km,"center":list(center.xyz),"grid":grid,"metrics":summarize([s for r in grid for s in r])}
    # 384 area-weighted planetary probes: deliberately sparse, not a species census.
    global_rows=[];area=vegetated_area=weighted_cover=0
    for face in range(6):
        for y in range(8):
            for x in range(8):
                key=CellKey(face,3,x,y);point=cell_center(key);s=sampler.sample(point)
                a=cell_solid_angle(key);land=s["source_evidence"]["water"]["macro_marine"] is False
                global_rows.append({"cell":[face,3,x,y],"point":list(point.xyz),"solid_angle":a,"land":land,"community":s})
                if land:
                    area+=a;weighted_cover+=a*s["cover_ppm"]
                    if s["established"]:vegetated_area+=a
                all_samples[s["community_id"]]=s
    report={"seed":seed,"radius_m":sampler.radius,"policy":policy,"signature":sampler.signature,
        "preparation_seconds":prep,"queries_seconds":time.perf_counter()-start,
        "queries":len(all_samples),"cache_entries":len(sampler.cache),
        "global_land_weighted_cover_ppm":weighted_cover/area if area else 0,
        "global_land_established_area_fraction":vegetated_area/area if area else 0,
        **summarize(list(all_samples.values())),"routes":routes,
        "windows":{k:v["metrics"] for k,v in windows.items()},
        "catalog_species":3096,"catalog_is_not_presence":True,
        "snapshot_semantics":"finite_established_founder_history_not_E1_candidates; offline_persisted_snapshots",
        "pending_extremes":96,"conditional_legacy_overlays_pending":8}
    for name,obj in (("report",report),("authority",sampler.descriptor),("communities",all_samples),("windows",windows),("planet",global_rows)):
        (folder/f"{name}.json").write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("seed","policy","species_established","dominant_species","physiognomies","preparation_seconds","queries_seconds")}),flush=True)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",nargs="+",type=int,default=[42,0,7,2026,12345]);p.add_argument("--policy",choices=["ecological_v1","exploration_mosaic_v1"],default="ecological_v1");p.add_argument("--quick",action="store_true")
    args=p.parse_args();reports=[]
    for seed in args.seeds:
        reports.append(run(seed,args.policy,quick=args.quick));gc.collect()
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/f"summary-{args.policy}.json").write_text(json.dumps(reports,indent=2),encoding="utf-8")


if __name__=="__main__":main()
