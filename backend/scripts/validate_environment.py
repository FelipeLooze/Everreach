"""E1 offline experiments from actual frozen World Genesis authorities."""
from collections import Counter
import json
from pathlib import Path
import time
import tracemalloc
from app.game.world.genesis.environment.adapter import EnvironmentSampler
from app.game.world.genesis.environment.catalog import load_environment_catalog
from app.game.world.genesis.environment.summary import summarize_environment
from app.game.world.genesis.geology.regional.experiment import window_point
from app.game.world.genesis.sphere_topology import CellKey,cell_center
from app.game.world.genesis.sphere_area import cell_solid_angle
from app.game.world.genesis.sphere_metric import from_lat_lon
from app.game.world.genesis.terrain.field import checksum
from scripts.validate_regional_geology import inputs as regional_inputs,land_windows
from scripts.preview_water import sources

ROOT=Path(__file__).resolve().parents[2]
SEEDS=(42,0,7,2026,12345)


def environment_inputs(seed,radius,config=None):
    regional=regional_inputs(seed,radius)
    _,h1,climate=sources(seed,radius)
    return EnvironmentSampler(regional,h1,climate,config)


def compact(sample):
    f=sample["logical_facts"];c=sample["physical_inputs"]
    return {"point":sample["point"],"probe_id":sample["probe_id"],"primary_potential":sample["primary_potential"],
        "secondary_potential":sample["secondary_potential"],"mixture":sample["mixture"],"ecotone":sample["ecotone"],
        "eligible":[r["environment_id"] for r in sample["results"] if r["state"]=="elegivel"],
        "states":dict(Counter(r["state"] for r in sample["results"])),
        "land":f["terreno.evidencia_superficie_continental"],"temperature_c":f["clima.temperatura_media_anual_c"],
        "rain_mm":f["clima.precipitacao_anual_mm"],"P_over_PET":f["clima.indice_aridez"],
        "height_m":f["terreno.altitude_m"],"slope_degrees":f["terreno.declividade_graus"],
        "substrates":c["substrates"],"feature_layers":sample["feature_layers"]}


def _metrics(samples):
    states=Counter();missing=Counter();pending_missing=Counter();confirmation_missing=Counter();conflicts=Counter();eligible=Counter();per_environment={};vegetation_pending=0
    for sample in samples:
        for r in sample["results"]:
            states[r["state"]]+=1
            missing.update(r["missing"]);conflicts.update(r["contradictions"])
            if r["state"]=="candidato_pendente":pending_missing.update(r["missing"])
            per_environment.setdefault(r["environment_id"],Counter())[r["state"]]+=1
            if r["state"]=="elegivel":
                eligible[r["environment_id"]]+=1
                confirmation_missing.update(r["confirmation_missing"])
                vegetation_pending+=r["vegetation_establishment_required"]
    return {"natural_state_counts":{s:states[s] for s in ("incompativel","candidato_pendente","elegivel","confirmado")},
        "built_state_counts":{"candidato_pendente":len(samples)*100},"anomalous_state_counts":{"candidato_pendente":len(samples)*50},
        "missing_by_field":dict(missing),"contradictions_by_field":dict(conflicts),
        "pending_missing_by_field":dict(pending_missing),"confirmation_requirements_pending":dict(confirmation_missing),
        "vegetation_establishment_pending":vegetation_pending,
        "per_environment_states":{k:dict(v) for k,v in per_environment.items()},
        "eligible_environment_ids":dict(eligible),"eligible_diversity":len(eligible),
        "primary_counts":dict(Counter(s["primary_potential"] or "unclassified" for s in samples)),
        "primary_diversity":len({s["primary_potential"] for s in samples if s["primary_potential"]}),
        "ecotone_samples":sum(s["ecotone"] for s in samples)}


def regional_window(sampler,center,width_m=1024000,intervals=12):
    points=[];grid=[]
    for y in range(intervals):
        row=[]
        for x in range(intervals):
            p=window_point(center,((2*x+1)*width_m//(2*intervals))-width_m//2,
                width_m//2-((2*y+1)*width_m//(2*intervals)),sampler.regional.sites.radius)
            s=sampler.sample(p);points.append(s);row.append(compact(s))
        grid.append(row)
    transitions=[]
    for y,row in enumerate(grid):
        for x,a in enumerate(row):
            for dx,dy in ((1,0),(0,1)):
                if y+dy<intervals and x+dx<intervals:
                    b=grid[y+dy][x+dx]
                    if a["land"] and b["land"] and a["primary_potential"]!=b["primary_potential"]:
                        transitions.append({"a":a,"b":b})
    return {"width_m":width_m,"sampling_intervals":intervals,"center":list(center.xyz),
        "samples":grid,"mosaic_contract":summarize_environment(points),"transitions":transitions[:12],"transition_edges":len(transitions),**_metrics(points)},points


def run(seed,radius,output):
    started=time.perf_counter();sampler=environment_inputs(seed,radius);preparation=time.perf_counter()-started
    before=checksum(sampler.regional.macro.to_dict()),checksum(sampler.climate.to_dict()),checksum(sampler.regional.terrain.plan.source.to_dict())
    samples=[];summaries=[];areas=Counter();land_area=0;gaps=0;climate_land=[];examples={}
    started=time.perf_counter()
    for face in range(6):
        for y in range(8):
            for x in range(8):
                key=CellKey(face,3,x,y);s=sampler.sample(cell_center(key));samples.append(s);short=compact(s);summaries.append(short)
                area=cell_solid_angle(key)*radius*radius/1e6
                areas[s["primary_potential"] or "unclassified"]+=area
                if short["land"]:
                    land_area+=area;climate_land.append(short)
                    gaps+=short["primary_potential"] is None
                    examples.setdefault("first_land",s)
                    if s["primary_potential"]:examples.setdefault("first_primary",s)
                    if s["ecotone"]:examples.setdefault("first_ecotone",s)
                    if any(r["state"]=="elegivel" and sampler.classifier.catalog["natural"][r["environment_id"]]["grupo"]=="florestas" for r in s["results"]):
                        examples.setdefault("first_forest_potential",s)
                    if s["feature_layers"]:examples.setdefault("first_layer",s)
                    if any(r["state"]=="elegivel" and not r["vegetation_establishment_required"] and not r["confirmation_missing"] for r in s["results"]):
                        examples.setdefault("first_physically_confirmable",s)
                else:examples.setdefault("first_marine_pending",s)
    query_seconds=time.perf_counter()-started
    metrics=_metrics(samples)
    ratios=[p["P_over_PET"] for p in climate_land if p["P_over_PET"] is not None]
    metrics.update(seed=seed,radius_m=radius,signature=sampler.signature,global_samples=len(samples),
        sampled_land_area_km2=land_area,primary_area_km2=dict(areas),unclassified_land_samples=gaps,
        land_sample_count=len(climate_land),climate_land={"mean_rain_mm":sum(p["rain_mm"] for p in climate_land)/len(climate_land),
            "temperature_range_c":[min(p["temperature_c"] for p in climate_land),max(p["temperature_c"] for p in climate_land)],
            "rain_range_mm":[min(p["rain_mm"] for p in climate_land),max(p["rain_mm"] for p in climate_land)],
            "P_over_PET_below_0_2":sum(v<0.2 for v in ratios),"P_over_PET_defined":len(ratios)},
        source_preparation_seconds=preparation,global_classification_seconds=query_seconds,
        runtime_generation_enabled=False,flora_fauna_loaded=False,confirmed_instances_in_statistics=0)
    folder=output/f"seed-{seed}-r{radius}";folder.mkdir(parents=True,exist_ok=True)
    regional=[]
    for index,center in enumerate(land_windows(sampler.regional)):
        window,window_samples=regional_window(sampler,center)
        regional.append({k:v for k,v in window.items() if k!="samples"})
        (folder/f"region-{index}.json").write_text(json.dumps(window,indent=2),encoding="utf-8")
        if seed in (42,2026) and radius==63710000:
            from app.game.world.genesis.environment.preview import write_region_preview
            write_region_preview(window,folder/f"region-{index}-environments.png",seed=seed)
            if index==0:
                write_region_preview(window,folder/"region-environments.png",seed=seed)
    metrics["regional"]=regional
    meridian=[compact(sampler.sample(from_lat_lon(lat,0))) for lat in range(-84,85,3)]
    (folder/"meridian.json").write_text(json.dumps(meridian,indent=2),encoding="utf-8")
    metrics["meridian_primary_diversity"]=len({p["primary_potential"] for p in meridian if p["primary_potential"]})
    metrics["physical_sources_unchanged"]=before==(checksum(sampler.regional.macro.to_dict()),checksum(sampler.climate.to_dict()),checksum(sampler.regional.terrain.plan.source.to_dict()))
    (folder/"metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    (folder/"global-samples.json").write_text(json.dumps(summaries,indent=2),encoding="utf-8")
    (folder/"examples.json").write_text(json.dumps(examples,indent=2),encoding="utf-8")
    if seed in (42,2026) and radius==63710000:
        from app.game.world.genesis.environment.preview import write_global_preview
        write_global_preview(summaries,sampler,folder/"planet-environments.png",seed=seed)
    print(json.dumps({k:metrics[k] for k in ("seed","radius_m","primary_diversity","eligible_diversity","unclassified_land_samples")}))
    return metrics,sampler,examples


def import_sources(db,sampler,seed):
    from app.db.models.world_genesis import GenesisWorld
    from app.db.models.world_hydrology import GenesisHydrologyPlan
    from app.db.models.world_climate import GenesisClimatePlan
    from app.db.models.world_geology import GenesisGeologyPlan
    from app.game.world.seed import create_campaign
    from app.game.world.genesis.terrain.service import initialize_terrain
    from app.game.world.genesis.geology.regional.service import initialize_regional_geology
    source=sampler.regional.terrain.plan.source;h1=sampler.h1;climate=sampler.climate;macro=sampler.regional.macro
    campaign=create_campaign(db,"E1 disposable proof",world_seed=seed);cid=campaign.id
    source_data=source.to_dict();hdata=h1.to_dict();cdata=climate.to_dict()
    db.add(GenesisWorld(campaign_id=cid,world_seed=seed,config=source.config.model_dump(),plan=source_data));db.flush()
    db.add(GenesisHydrologyPlan(campaign_id=cid,hydrology_version=1,source_signature=source.signature,
        source_checksum=checksum(source_data),signature=h1.signature,config=h1.config.model_dump(),payload_checksum=checksum(hdata),plan=hdata));db.flush()
    db.add(GenesisClimatePlan(campaign_id=cid,climate_version=climate.config.climate_version,source_signature=source.signature,source_checksum=checksum(source_data),
        hydrology_signature=h1.signature,hydrology_checksum=checksum(hdata),signature=climate.signature,
        config=climate.config.model_dump(),payload_checksum=checksum(cdata),plan=cdata));db.flush()
    initialize_terrain(db,cid,sampler.regional.terrain.plan.config)
    db.add(GenesisGeologyPlan(campaign_id=cid,geology_version=1,signature=macro.signature,baseline=macro.to_dict(),baseline_checksum=checksum(macro.to_dict())));db.flush()
    initialize_regional_geology(db,cid,sampler.regional.config)
    return cid


def persistence_demo(sampler,examples,output):
    import tempfile
    from sqlalchemy import create_engine,event
    from sqlalchemy.orm import Session
    from app.db import models
    from app.db.base import Base
    from app.db.database import enable_sqlite_foreign_keys
    from app.db.models.world_geology import GenesisMineralDeposit
    from app.game.world.genesis.environment.service import initialize_environment,materialize_environment_point,query_environment
    from app.game.world.genesis.sphere_topology import SurfacePoint
    chosen={s["probe_id"]:s for s in examples.values()}
    with tempfile.TemporaryDirectory(prefix="everreach-e1-") as directory:
        engine=create_engine(f"sqlite:///{Path(directory,'proof.db').as_posix()}")
        event.listen(engine,"connect",enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
        with Session(engine) as db:
            cid=import_sources(db,sampler,42);initialize_environment(db,cid,sampler.config)
            stored=[]
            for sample in reversed(list(chosen.values())):
                row=materialize_environment_point(db,cid,SurfacePoint(*sample["point"]));stored.append(row.baseline)
            assert db.query(GenesisMineralDeposit).count()==0
            db.commit()
        with Session(engine) as db:
            for sample in stored:
                again=query_environment(db,cid,SurfacePoint(*sample["point"]))
                assert again["baseline"]==sample
                materialize_environment_point(db,cid,SurfacePoint(*sample["point"]))
            assert db.query(GenesisMineralDeposit).count()==0
        engine.dispose()
    proof={"seed":42,"radius_m":sampler.regional.sites.radius,"committed_and_reopened":True,
        "points":stored,"natural_state_counts":dict(Counter(r["state"] for s in stored for r in s["results"])),
        "species_or_mineral_sources_created":0,"real_save_modified":False}
    (output/"persistent-proof.json").write_text(json.dumps(proof,indent=2),encoding="utf-8")
    return {"points":len(stored),"states":proof["natural_state_counts"]}


def main():
    output=ROOT/"artifacts/environment-e1";output.mkdir(parents=True,exist_ok=True)
    metrics=[];persisted=None
    for seed,radius in [(s,63710000) for s in SEEDS]+[(42,r) for r in (6371000,637100000,1000000000000)]:
        result,sampler,examples=run(seed,radius,output);metrics.append(result)
        if seed==42 and radius==63710000:
            persisted=persistence_demo(sampler,examples,output)
    sampler=environment_inputs(42,63710000);points=[cell_center(CellKey(0,3,x,y)) for x in range(8) for y in range(8)]
    tracemalloc.start();started=time.perf_counter()
    for p in points:sampler.sample(p)
    elapsed=time.perf_counter()-started;retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    suite={"cases":metrics,"persisted_demo":persisted,"catalog":load_environment_catalog()["hashes"],
        "benchmark":{"instrumented_points":len(points),"seconds":elapsed,"peak_bytes":peak,"retained_bytes":retained,
            "scope":"E1 queries including T1/JR1 caches; physical global plans loaded; not RSS"},
        "runtime_generation_enabled":False,"C2_modified":False,"flora_fauna_loaded":False,"real_save_modified":False}
    (output/"suite.json").write_text(json.dumps(suite,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
