"""One real Uvicorn smoke for WGS2.3.1; all state stays in temporary SQLite."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from time import perf_counter, sleep
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _hidden_coordinates(value):
    if isinstance(value, dict):
        return any(k in {"genesis_site", "spatial_contract", "from_point", "to_point", "physical_point"}
                   or _hidden_coordinates(v) for k, v in value.items())
    return isinstance(value, list) and any(_hidden_coordinates(v) for v in value)


def main():
    profile = sys.argv[1] if len(sys.argv) > 1 else "world_genesis_ap1_tp1_wgs2_v4"
    controlled_variety = len(sys.argv) > 2 and sys.argv[2] == "controlled-variety"
    controlled_water = len(sys.argv) > 2 and sys.argv[2] == "controlled-water"
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    if profile not in ("world_genesis_ap1_tp1_wgs2_v4", "world_genesis_ap1_tp1_wgs2_v5",
                       "world_genesis_ap1_tp1_wgs3_v1"):
        raise ValueError("Unsupported WGS2 canonical smoke profile")
    if controlled_variety and profile != "world_genesis_ap1_tp1_wgs2_v5":
        raise ValueError("Controlled variety requires the V5 profile")
    if controlled_water and profile != "world_genesis_ap1_tp1_wgs3_v1":
        raise ValueError("Controlled water requires the WGS3 profile")
    backend = Path(__file__).resolve().parents[1]
    primary = backend / "everreach.db"
    digest = hashlib.sha256(primary.read_bytes()).hexdigest() if primary.exists() else None
    folder = Path(tempfile.mkdtemp(prefix="everreach-wgs2-3-1-http-"))
    database_url = "sqlite:///" + (folder / "smoke.sqlite").as_posix()
    env = {**os.environ, "DATABASE_URL":database_url, "PYTHONIOENCODING":"utf-8"}
    for role in ("INTENT", "NARRATIVE", "REGENERATION"):
        env[role+"_LLM_PROVIDER"] = "disabled"
        env[role+"_LLM_FALLBACK_PROVIDER"] = ""
        env[role+"_LLM_FALLBACK_MODEL"] = ""
    subprocess.run([sys.executable,"-m","alembic","upgrade","head"],cwd=backend,env=env,
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    base=f"http://127.0.0.1:{port}"
    def request(path, body=None):
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(base+path,data=payload,headers={"Content-Type":"application/json"})
        try:
            with urlopen(req,timeout=300) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"{path}: HTTP {exc.code}: {exc.read().decode('utf-8')}") from exc
    log = (folder/"uvicorn.log").open("a",encoding="utf-8")
    def launch():
        process=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1",
            "--port",str(port)],cwd=backend,env=env,stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        for _ in range(240):
            if process.poll() is not None: raise RuntimeError(f"Uvicorn exited: {folder/'uvicorn.log'}")
            try: request("/openapi.json"); return process
            except OSError: sleep(.25)
        process.terminate(); process.wait(timeout=30)
        raise RuntimeError("Uvicorn startup timeout")
    process=launch()
    try:
        campaign=request("/api/campaigns",{"name":"WGS canonical smoke","world_seed":seed,
            "world_profile":profile})
        cid=campaign["id"]
        actor=request(f"/api/campaigns/{cid}/characters",{"name":"Exploradora"}); aid=actor["id"]
        prefix=f"/api/campaigns/{cid}"; query=f"?character_id={aid}"
        start=perf_counter(); started=request(prefix+"/start"+query,{}); start_seconds=perf_counter()-start
        root=started["state"]["location"]["id"]
        request(prefix+"/actions"+query,{"text":"Olho ao redor.","action_key":"canonical-observe-root"})
        plants=request(prefix+"/actions"+query,{"text":"Observo as plantas próximas.",
            "action_key":"canonical-plants","plant_action":{"kind":"look"}})
        os.environ["DATABASE_URL"]=database_url
        from app.db.database import SessionLocal
        from app.db.models.location import Location, LocationConnection
        from app.db.models.campaign import Campaign
        with SessionLocal() as db:
            edges=db.query(LocationConnection).filter_by(from_location_id=root,active=True).all()
            edge=next(e for e in edges if (db.get(Location,e.to_location_id) is not None
                and db.get(Location,e.to_location_id).type == "genesis_field"))
            direction,target=edge.direction,edge.to_location_id
            state=db.get(Campaign,cid).playable_state
            assert state["microhabitats"]["canonical_resolution_version"] == "WGS2_CANONICAL_MICRO_R1"
        water_probe = None
        if controlled_water:
            from app.db.models.world_natural_formations import GenesisLocalWaterBody
            from app.game.world.genesis import local_formations
            from app.game.world.genesis.local_water import contract as local_water_contract
            from app.game.world.genesis.sphere_topology import CellKey, cell_center
            from app.game.world.genesis.environment.service import materialize_environment_point
            import app.game.world.genesis.wgs2_families as families
            with SessionLocal() as db:
                current_campaign = db.get(Campaign,cid)
                field = db.get(Location,target)
                address = field.genesis_site["cell"]
                materialize_environment_point(db,cid,cell_center(CellKey(**address)))
                original_candidate=families.candidate
                families.candidate=lambda seed,address_arg,records,**kw: (
                    "EV-LOC-0068" if address_arg == address else original_candidate(seed,address_arg,records,**kw))
                try:
                    source=local_formations.materialize_for_site(db,current_campaign,field,_skip_origin_lookup=True)
                finally:
                    families.candidate=original_candidate
                if source is None or source.archetype_id != "EV-LOC-0068":
                    raise AssertionError("Controlled real-evidence spring was not materialized")
                initial=local_water_contract(db,source)
                water_probe={"formation_id":source.id,"location_id":source.location_id,"source_key":initial["source_key"],
                    "signature":initial["signature"],"available_litres":initial["available_litres"]}
                db.commit()
        t=perf_counter(); moved=request(prefix+"/actions"+query,{"text":"Vou para "+direction+".","action_key":"canonical-move"})
        move_seconds=perf_counter()-t
        if moved["state"]["location"]["id"] != target:
            raise AssertionError("TP1 movement did not reach the selected adjacent field")
        if controlled_water:
            request(prefix+"/actions"+query,{"text":"Olho ao redor.","action_key":"spring-observe-field"})
            with SessionLocal() as db:
                spring_edge=db.query(LocationConnection).filter_by(
                    from_location_id=target,to_location_id=water_probe["location_id"],active=True).one()
            arrived=request(prefix+"/actions"+query,{"text":"Vou para "+spring_edge.direction+".",
                "action_key":"spring-enter"})
            if arrived["state"]["location"]["id"] != water_probe["location_id"]:
                raise AssertionError("Spring access did not use the existing travel graph")
            inspected=request(prefix+"/actions"+query,{"text":"Inspeciono a nascente.",
                "action_key":"spring-inspect","formation_action":{"kind":"inspect"}})
            inspection=json.loads(inspected["mechanical_summary"])
            water=inspection["water_source"]
            if (water["source_key"] != water_probe["source_key"] or
                    water["available_litres"] != water_probe["available_litres"] or
                    water["collectable"] or water["stored_in_container"] or
                    water["consumed_or_transferred"] or "water" in inspection or
                    any(key in water for key in ("point","origin_authority"))):
                raise AssertionError("HTTP source facts differ or expose internal coordinates")
            request(prefix+"/actions"+query,{"text":"Examino a fonte.",
                "action_key":"spring-interact","formation_action":{"kind":"interact"}})
            with SessionLocal() as db:
                current=db.get(GenesisLocalWaterBody,water_probe["formation_id"])
                if (current.stored_litres,current.revision) != (water_probe["available_litres"],0):
                    raise AssertionError("Read-only interaction changed the spring stock")
                return_edge=db.query(LocationConnection).filter_by(
                    from_location_id=water_probe["location_id"],to_location_id=target,active=True).one()
            returned=request(prefix+"/actions"+query,{"text":"Vou para "+return_edge.direction+".",
                "action_key":"spring-return"})
            if returned["state"]["location"]["id"] != target:
                raise AssertionError("Spring return route failed")
        before=request(prefix+"/map-view"+query)
        if _hidden_coordinates(before): raise AssertionError("Map exposed hidden spatial fields")
        process.terminate(); process.wait(timeout=30); process=launch()
        resumed=request(prefix+"/start"+query,{})
        if resumed["state"]["location"]["id"] != target: raise AssertionError("Location changed after restart")
        after=request(prefix+"/map-view"+query)
        if before != after or _hidden_coordinates(after): raise AssertionError("Map changed or exposed coordinates after restart")
        observation=request(prefix+"/actions"+query,{"text":"Olho ao redor.","action_key":"canonical-after-restart"})
        if controlled_water:
            revisited=request(prefix+"/actions"+query,{"text":"Vou para "+spring_edge.direction+".",
                "action_key":"spring-revisit"})
            if revisited["state"]["location"]["id"] != water_probe["location_id"]:
                raise AssertionError("Spring identity changed after restart")
            after_inspection=request(prefix+"/actions"+query,{"text":"Inspeciono novamente a nascente.",
                "action_key":"spring-inspect-after-restart","formation_action":{"kind":"inspect"}})
            after_water=json.loads(after_inspection["mechanical_summary"])["water_source"]
            if (after_water["source_key"] != water_probe["source_key"] or
                    after_water["signature"] != water_probe["signature"] or
                    after_water["available_litres"] != water_probe["available_litres"]):
                raise AssertionError("Spring stock or signature changed after restart")
        controlled = None
        if controlled_variety:
            from app.db.models.location import Location
            from app.db.models.world_spatial import LocationSpatialAnchor
            from app.db.models.campaign import Campaign
            from app.db.models.character import Character
            from app.game.world.genesis import local_formations
            from app.game.world.genesis.sphere_topology import CellKey, cell_center
            import app.game.world.genesis.wgs2_families as families
            cells = {
                (0, 17, 100000, 30000): "EV-LOC-0037",
                (0, 17, 100010, 30000): "EV-LOC-0051",
                (0, 17, 100020, 30000): "EV-LOC-0082",
                (0, 17, 120000, 120000): "EV-LOC-0023",
            }
            original_candidate = families.candidate
            families.candidate = lambda seed, address, records, **kw: cells.get(tuple(
                address[key] for key in ("face", "level", "x", "y")))
            created = []
            try:
                with SessionLocal() as db:
                    current_campaign = db.get(Campaign, cid)
                    root_location = db.get(Location, root)
                    for coords, archetype in cells.items():
                        cell = CellKey(*coords)
                        point = cell_center(cell)
                        exterior = Location(region_id=root_location.region_id, name="Controlled field",
                            type="genesis_field", genesis_site={"version":"territory_tp1",
                            "cell":vars(cell),"point":list(point.xyz),"prepared":True})
                        db.add(exterior); db.flush()
                        db.add(LocationSpatialAnchor(location_id=exterior.id,campaign_id=cid,
                            point=list(point.xyz)))
                        instance = local_formations.materialize_for_site(db, current_campaign, exterior,
                            _skip_origin_lookup=True)
                        if instance is None or instance.archetype_id != archetype:
                            raise AssertionError(f"Controlled real-evidence site failed: {archetype}")
                        created.append((archetype, instance.location_id,
                                        instance.data.get("interior_location_id"),
                                        instance.data.get("subarea_location_ids", [])))
                    db.commit()
            finally:
                families.candidate = original_candidate
            for index, (archetype, location_id, interior_id, subarea_ids) in enumerate(created):
                with SessionLocal() as db:
                    db.get(Character, aid).location_id = location_id
                    db.commit()
                inspected = request(prefix+"/actions"+query,{"text":"Inspeciono a formacao.",
                    "action_key":f"controlled-inspect-{index}","formation_action":{"kind":"inspect"}})
                summary = json.loads(inspected["mechanical_summary"])
                if summary["identity"]["archetype_id"] != archetype:
                    raise AssertionError("HTTP formation identity mismatch")
                investigated = request(prefix+"/actions"+query,{"text":"Investigo a formacao.",
                    "action_key":f"controlled-interact-{index}","formation_action":{"kind":"interact"}})
                if "investigated" not in json.loads(investigated["mechanical_summary"]):
                    raise AssertionError("HTTP investigation facts missing")
                child = interior_id or (subarea_ids[0] if subarea_ids else None)
                if child:
                    with SessionLocal() as db:
                        db.get(Character, aid).location_id = child
                        db.commit()
                    child_result = request(prefix+"/actions"+query,{"text":"Inspeciono o interior.",
                        "action_key":f"controlled-child-{index}","formation_action":{"kind":"inspect"}})
                    if json.loads(child_result["mechanical_summary"])["identity"]["archetype_id"] != archetype:
                        raise AssertionError("HTTP child inspection mismatch")
            controlled = {"archetypes":[item[0] for item in created],
                          "inspections":len(created),"investigations":len(created),
                          "child_inspections":sum(bool(item[2] or item[3]) for item in created),
                          "selection_forced_only_in_fixture":True}
            process.terminate(); process.wait(timeout=30); process=launch()
            persisted = request(prefix+"/actions"+query,{"text":"Inspeciono novamente.",
                "action_key":"controlled-after-restart","formation_action":{"kind":"inspect"}})
            if json.loads(persisted["mechanical_summary"])["identity"]["archetype_id"] != created[-1][0]:
                raise AssertionError("Controlled formation identity changed after server restart")
            controlled["inspection_after_server_restart"] = True
        result={"profile":profile,"seed":seed,"start_seconds":round(start_seconds,3),
            "movement_seconds":round(move_seconds,3),"created_and_started":True,"plant_query":plants.get("plant_result") is not None,
            "movement_succeeded":True,"restart_preserved_location_and_map":True,
            "observation_after_restart":bool(observation.get("mechanical_summary")),"public_map_coordinate_leaks":False,
            "database":str(folder/"smoke.sqlite")}
        if controlled is not None:
            result["controlled_variety"] = controlled
        if water_probe is not None:
            result["controlled_water"] = {"source_key":water_probe["source_key"],
                "available_litres":water_probe["available_litres"],
                "observed_inspected_interacted_returned_revisited":True,
                "stock_preserved_after_restart":True,"collection_enabled":False,
                "selection_forced_only_in_fixture":True}
        (folder/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        process.terminate(); process.wait(timeout=30); log.close()
        current=hashlib.sha256(primary.read_bytes()).hexdigest() if primary.exists() else None
        if current != digest: raise AssertionError("The primary database changed during isolated smoke")


if __name__ == "__main__":
    main()
