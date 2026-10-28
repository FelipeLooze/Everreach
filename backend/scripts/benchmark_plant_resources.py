"""Bounded R1 estimates and production resolver timings in an isolated database."""
import json,time,tracemalloc
from sqlalchemy import create_engine,event
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.game.world.genesis.vegetation import service
from app.game.world.genesis.vegetation.resources import derive,load_flora_catalog,initialize_resources
from app.game.world.genesis.vegetation.actions import resolve_plant_action,encounter
from app.schemas.action import PlantActionRequest
from scripts.validate_plant_resources import inputs,actual_individual,prepare_operator,set_window,OUT
from scripts.prove_vegetation import prepare


def main():
    cat=load_flora_catalog();sp=cat.species["EV-FL-1501"]
    start=time.perf_counter()
    for i in range(1000):derive(sp,1000+i)
    derivation=time.perf_counter()-start
    tracemalloc.start()
    for i in range(1000):derive(sp,1000+i)
    retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    sampler=inputs(42);engine=create_engine("sqlite:///:memory:");event.listen(engine,"connect",enable_sqlite_foreign_keys);Base.metadata.create_all(engine)
    with Session(engine) as db:
        cid=prepare(db,sampler);initialize_resources(db,cid,experimental=True)
        start=time.perf_counter();point,ind,part=actual_individual(db,cid,sampler,42,"flor");materialize=time.perf_counter()-start
        actor,tool=prepare_operator(db,cid,ind,sampler);set_window(db,cid,part,ind,sampler)
        start=time.perf_counter();look=encounter(db,cid,actor);look_time=time.perf_counter()-start
        req=PlantActionRequest(kind="harvest",individual_id=ind.individual_id,part_id=part["id"],quantity=1,tool_instance_id=tool.id)
        start=time.perf_counter();result=resolve_plant_action(db,cid,actor.id,req,"benchmark");harvest=time.perf_counter()-start
        start=time.perf_counter();resolve_plant_action(db,cid,actor.id,req,"benchmark");replay=time.perf_counter()-start
        report={"derived_profiles":1000,"untraced_derivation_seconds":derivation,"mean_derivation_ms":derivation,
            "traced_retained_bytes":retained,"traced_peak_bytes":peak,"catalog_and_sources_excluded_from_memory":True,
            "materialization_seconds":materialize,"local_look_seconds":look_time,"visible_individuals":len(look),
            "harvest_resolver_seconds":harvest,"replay_resolver_seconds":replay,"scope":"resolver_and_storage; excludes HTTP checkpoint whole-database snapshot",
            "global_population_enumerated":False}
        OUT.mkdir(parents=True,exist_ok=True);(OUT/"benchmark.json").write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps(report),flush=True)
    engine.dispose()


if __name__=="__main__":main()
