"""JR1 offline validation on predetermined seeds/windows, disposable SQLite only."""
import json
from pathlib import Path
from collections import Counter
import time
import tracemalloc
from app.game.world.genesis.geology.field import load_geology_plan,build_geology_plan
from app.game.world.genesis.geology.catalog import load_catalog
from app.game.world.genesis.geology.regional.field import RegionalSampler
from app.game.world.genesis.geology.regional.occurrence import opportunities,select_sources,INTENSITY_PER_KM_PPM
from app.game.world.genesis.geology.regional.config import RegionalPolicy
from app.game.world.genesis.geology.regional.experiment import window_formations,measure_window,cross_sector_points
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.sphere_metric import distance_m
from app.game.world.genesis.terrain.field import TerrainSampler,build_terrain_plan,checksum
from scripts.validate_geology import source_plan

ROOT = Path(__file__).resolve().parents[2]
SEEDS = (42,0,7,2026,12345)


def inputs(seed,radius):
    source = source_plan(seed,radius)
    terrain = TerrainSampler(build_terrain_plan(source))
    path = ROOT/f"artifacts/geology-j1/seed-{seed}-r{radius}/plan.json"
    macro = load_geology_plan(json.loads(path.read_text()),terrain.plan) if path.exists() else build_geology_plan(terrain.plan)
    return RegionalSampler(macro,terrain)


def land_windows(sampler):
    return [SurfacePoint(*u["center"]) for u in sampler.macro.units
        if sampler.terrain.sample(SurfacePoint(*u["center"]))["height_mm"]>sampler.terrain.plan.source.config.sea_level_m*1000][:3]


def nn_summary(points,config):
    unique = list({tuple(p) for p in points})
    if len(unique)<2:
        return {"locations":len(unique),"nearest_km_min":None,"nearest_km_median":None}
    distances = sorted(min(distance_m(config,SurfacePoint(*p),SurfacePoint(*q)) for j,q in enumerate(unique) if j!=i)/1000
        for i,p in enumerate(unique))
    return {"locations":len(unique),"nearest_km_min":distances[0],"nearest_km_median":distances[len(distances)//2]}


def run(seed,radius,index,output):
    sampler = inputs(seed,radius)
    center = land_windows(sampler)[index]
    before = checksum(sampler.macro.to_dict()),checksum(sampler.terrain.plan.source.to_dict())
    started = time.perf_counter()
    forms,budget = window_formations(sampler,center)
    prepared = time.perf_counter()-started
    measured = measure_window(sampler,center)
    catalog = load_catalog()
    assessments = {k:opportunities(f,sampler.signature,catalog) for k,f in forms.items()}
    all_opps = [o for a in assessments.values() for o in a["opportunities"]]
    selected = [d for f in forms.values() for d in select_sources(f,sampler.signature,catalog=catalog)]
    land = [d for d in selected if d["exposure_model"]["anchor_terrestrial_baseline"]]
    common = [d for d in land if d["rarity"]=="comum"]
    exposed = [d for d in common if d["exposure_model"]["rock_outcrop_model"]]
    summary = {"seed":seed,"radius_m":radius,"window_index":index,"window_center":list(center.xyz),
        "geographic_selection":"first_three_J1_centers_above_sea_by_slot_before_mineral_assessment",
        "authority_signature":sampler.signature,"forms":len(forms),"provinces":len({f["parent_unit_id"] for f in forms.values()}),
        "lithologies":dict(Counter(f["substrates"][0] for f in forms.values())),
        "opportunities":len(all_opps),"eligible_structure_length_km":sum(f["structure_length_m"] for k,f in forms.items() if assessments[k]["opportunities"])/1000,
        "selected_sources":len(selected),"terrestrial_sources":len(land),"common_terrestrial_sources":len(common),
        "common_outcrop_model_sources":len(exposed),"by_rarity":dict(Counter(d["rarity"] for d in selected)),
        "common_land_sources_per_1000_km2":1000*len(common)/measured["land_area_km2"] if measured["land_area_km2"] else None,
        "per_material_terrestrial_sources":dict(Counter(d["material_id"] for d in land)),
        "nearest_distinct_common_source_sites":nn_summary([d["anchor_surface_point"] for d in common],sampler.terrain.plan.source.config),
        "iron_nearest":nn_summary([d["anchor_surface_point"] for d in land if d["material_id"]=="EV-GEO-FAN-0001"],sampler.terrain.plan.source.config),
        "sensitivity_counts":{str(factor):sum(len(select_sources(f,sampler.signature,RegionalPolicy(rate_factor_ppm=factor),catalog)) for f in forms.values())
            for factor in (0,500000,1000000,2000000)},
        "prepare_seconds":prepared,"enumeration":budget,"measurement":{k:v for k,v in measured.items() if k!="raster"},
        "formation_cache_size":len(sampler.cache),"site_cache_size":len(sampler.sites.cache),
        "parent_J1_and_V4_unchanged":before==(checksum(sampler.macro.to_dict()),checksum(sampler.terrain.plan.source.to_dict())),
        "sources_instantiated_by_statistics":0,"runtime_generation_enabled":False}
    folder = output/f"seed-{seed}-r{radius}-w{index}"
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"metrics.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    (folder/"formations.json").write_text(json.dumps(forms,indent=2),encoding="utf-8")
    (folder/"selected-test-sources.json").write_text(json.dumps(selected,indent=2),encoding="utf-8")
    if radius==63710000 and ((seed in (42,0) and index==0) or (seed in (42,2026) and index==2)):
        from app.game.world.genesis.geology.regional.preview import write_preview
        write_preview(sampler,center,forms,selected,measured,folder/"regional-geology.png",seed=seed)
    print(json.dumps({k:summary[k] for k in ("seed","radius_m","window_index","forms","opportunities","selected_sources","common_terrestrial_sources")}))
    return summary,sampler,forms,selected


def persistence_demo(seed,radius,sampler,formations,selected,folder):
    import tempfile
    from sqlalchemy import create_engine,event
    from sqlalchemy.orm import Session
    from app.db.base import Base
    from app.db.database import enable_sqlite_foreign_keys
    from app.db.models.world_genesis import GenesisWorld
    from app.db.models.world_geology import GenesisGeologyPlan,GenesisMineralDeposit
    from app.db.models.world_geology_regional import GenesisRegionalFormation
    from app.game.world.seed import create_campaign
    from app.game.world.genesis.service import initialize_world
    from app.game.world.genesis.formation_v4 import FormationConfigV4
    from app.game.world.genesis.terrain.service import initialize_terrain
    from app.game.world.genesis.geology.service import initialize_geology
    from app.game.world.genesis.geology.regional.service import initialize_regional_geology,materialize_regional_formation,query_regional_geology
    if not selected:
        return None
    candidates=sorted((d for d in selected if d["exposure_model"]["anchor_terrestrial_baseline"] and d["rarity"]=="comum"),key=lambda d:d["deposit_id"])
    source=candidates[0];witness=None
    for candidate in candidates:
        test=cross_sector_points(sampler,formations[candidate["formation_id"]])
        if test:
            source,witness=candidate,test
            break
    point = SurfacePoint(*source["anchor_surface_point"])
    with tempfile.TemporaryDirectory(prefix="everreach-jr1-") as directory:
        engine=create_engine(f"sqlite:///{Path(directory,'proof.db').as_posix()}")
        event.listen(engine,"connect",enable_sqlite_foreign_keys)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            campaign=create_campaign(db,"JR1 disposable proof",world_seed=seed)
            initialize_world(db,campaign.id,FormationConfigV4(radius_m=radius))
            initialize_terrain(db,campaign.id);initialize_geology(db,campaign.id);initialize_regional_geology(db,campaign.id)
            original = checksum(db.get(GenesisWorld,campaign.id).plan)
            original_J1 = checksum(db.get(GenesisGeologyPlan,campaign.id).baseline)
            started=time.perf_counter()
            row=materialize_regional_formation(db,campaign.id,point,experimental_sources=True)
            for formation in reversed(sorted(formations.values(),key=lambda f:f["formation_id"])):
                if formation["formation_id"]!=row.formation_id:
                    materialize_regional_formation(db,campaign.id,SurfacePoint(*formation["anchor_point"]),experimental_sources=True)
            materialization_seconds=time.perf_counter()-started
            result=query_regional_geology(db,campaign.id,point)
            cid,identifier=campaign.id,row.formation_id
            assert row.baseline==formations[identifier]
            db.commit()
        with Session(engine) as db:
            materialize_regional_formation(db,cid,point,experimental_sources=True)
            again=query_regional_geology(db,cid,point)
            assert again==result and checksum(db.get(GenesisWorld,cid).plan)==original
            assert checksum(db.get(GenesisGeologyPlan,cid).baseline)==original_J1
            rows=db.query(GenesisMineralDeposit).filter_by(campaign_id=cid).order_by(GenesisMineralDeposit.deposit_id).all()
            assert {r.deposit_id for r in rows}=={d["deposit_id"] for d in selected}
            expected={d["deposit_id"]:d for d in selected}
            for r in rows:
                assert r.baseline=={**expected[r.deposit_id],"eligible_not_instantiated":False,"state":"experimental_instantiated"}
                assert r.remaining_units==expected[r.deposit_id]["initial_volume_units"]
            persisted_count=len(rows)
            persisted_formations=db.query(GenesisRegionalFormation).filter_by(campaign_id=cid).count()
            assert persisted_formations==len(formations)
            stocks=[{"deposit_id":r.deposit_id,"material_id":r.baseline["material_id"],
                "formation_id":r.baseline["formation_id"],"remaining_units":r.remaining_units} for r in rows]
            if witness:
                for view in witness:
                    materialize_regional_formation(db,cid,SurfacePoint(*view["point"]),experimental_sources=True)
                    assert query_regional_geology(db,cid,SurfacePoint(*view["point"]))["sources"]==result["sources"]
        engine.dispose()
    proof={"seed":seed,"radius_m":radius,"committed_and_reopened":True,"result":result,
        "real_save_modified":False,"finite_stock_table":"genesis_mineral_deposits",
        "persisted_formations":persisted_formations,"persisted_sources":persisted_count,"finite_stocks":stocks,
        "materialization_seconds":materialization_seconds,"J1_and_V4_preserved":True,
        "cross_sector_witness":witness,"cross_sector_stock_shared_by_formation_id":bool(witness)}
    (folder/"persistent-proof.json").write_text(json.dumps(proof,indent=2),encoding="utf-8")
    return persisted_count


def main():
    output=ROOT/"artifacts/geology-jr1";output.mkdir(parents=True,exist_ok=True)
    cases=[(seed,63710000,i) for seed in SEEDS for i in range(3)]+[(42,r,0) for r in (6371000,637100000,1000000000000)]
    summaries=[];persisted=0
    for seed,radius,index in cases:
        summary,sampler,forms,selected=run(seed,radius,index,output);summaries.append(summary)
        if seed==42 and radius==63710000 and index==0:
            persisted=persistence_demo(seed,radius,sampler,forms,selected,output/f"seed-{seed}-r{radius}-w{index}") or 0
    sampler=inputs(42,63710000);center=land_windows(sampler)[0]
    tracemalloc.start();started=time.perf_counter();forms,_=window_formations(sampler,center)
    elapsed=time.perf_counter()-started;retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    suite={"cases":summaries,"intensity_per_eligible_km_ppm":INTENSITY_PER_KM_PPM,"global_fixed_caps":False,
        "persisted_experimental_sources":persisted,"benchmark":{"window_preparation_instrumented_seconds":elapsed,
            "peak_bytes":peak,"retained_bytes":retained,"forms":len(forms),"scope":"JR1 physical window; macro J1/V4/T1 loaded; not RSS"},
        "real_save_modified":False,"runtime_generation_enabled":False}
    (output/"suite.json").write_text(json.dumps(suite,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
