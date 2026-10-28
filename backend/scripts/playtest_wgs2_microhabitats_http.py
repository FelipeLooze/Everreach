"""Controlled WGS2.3 microhabitat journey on temporary SQLite and real Uvicorn.

The fixture is prepared through the existing materializer before the actor's
route begins. Only the test process pins the selector for one eligible cell;
the running API, discovery, travel, inspection and restart paths are ordinary.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    backend = Path(__file__).resolve().parents[1]
    main_db = backend / "everreach.db"
    main_hash = hashlib.sha256(main_db.read_bytes()).hexdigest() if main_db.exists() else None
    folder = Path(tempfile.mkdtemp(prefix="everreach-wgs2-3-http-"))
    dbpath = folder / "playtest.sqlite"
    url = "sqlite:///" + dbpath.as_posix()
    env = {**os.environ, "DATABASE_URL": url, "PYTHONIOENCODING": "utf-8"}
    for role in ("INTENT", "NARRATIVE", "REGENERATION"):
        env[role + "_LLM_PROVIDER"] = "disabled"
        env[role + "_LLM_FALLBACK_PROVIDER"] = ""
        env[role + "_LLM_FALLBACK_MODEL"] = ""
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend,
                   env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def request(path, body=None):
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(base + path, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=300) as response:
                return json.load(response)
        except HTTPError as exc:
            raise AssertionError(f"{path} {exc.code}: {exc.read().decode('utf-8')}") from exc

    log = (folder / "uvicorn.log").open("a", encoding="utf-8")

    def launch():
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", str(port)], cwd=backend, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(240):
            if process.poll() is not None:
                raise RuntimeError(f"Uvicorn exited; inspect {folder / 'uvicorn.log'}")
            try:
                request("/openapi.json"); return process
            except OSError:
                time.sleep(0.25)
        process.terminate(); process.wait(timeout=30)
        raise RuntimeError("Uvicorn startup timeout")

    process = launch()
    try:
        campaign = request("/api/campaigns", {"name":"WGS2.3 controlled microhabitat journey",
            "world_profile":"world_genesis_ap1_tp1_wgs2_v3", "world_seed":42})
        cid = campaign["id"]
        actor = request(f"/api/campaigns/{cid}/characters", {"name":"Exploradora"})
        aid = actor["id"]
        prefix, query = f"/api/campaigns/{cid}", f"?character_id={aid}"
        started = time.perf_counter(); initial = request(prefix + "/start" + query, {})
        start_seconds = time.perf_counter() - started
        root_id = initial["state"]["location"]["id"]

        # Set up one controlled, physically eligible v24 fixture before the
        # character explores it. No production selector or route code changes.
        os.environ["DATABASE_URL"] = url
        from app.db.database import SessionLocal
        from app.db.models.campaign import Campaign as CampaignModel
        from app.db.models.location import CharacterLocationDiscovery, Location, LocationConnection
        from app.db.models.world_natural_formations import GenesisFormationCoverageCell, GenesisNaturalFormation
        from app.db.models.world_vegetation import GenesisPlantIndividual
        from app.db.models.world_spatial import LocationSpatialAnchor
        from app.game.world.genesis.local_formations import catalog, materialize_for_site
        from app.game.world.genesis.environment.service import materialize_environment_point, query_environment
        from app.game.world.genesis.sphere_topology import CellKey, DIRECTIONS, SurfacePoint, neighbor
        from app.game.world.genesis.territory import prepare_site
        from app.game.world.genesis.wgs2_families import VERSION_V2, candidate as selector, eligibility
        import app.game.world.genesis.local_formations as local_formations
        import app.game.world.genesis.wgs2_families as wgs2_families

        fixture = SessionLocal()
        fixture.expire_on_commit = False
        try:
            campaign_row = fixture.get(CampaignModel, cid)
            root = fixture.get(Location, root_id)
            root_key = CellKey(**root.genesis_site["cell"])
            outgoing = (fixture.query(LocationConnection)
                .filter_by(from_location_id=root.id, active=True).all())
            choices = []
            records = catalog()
            original_selector = wgs2_families.candidate
            for edge in outgoing:
                destination = fixture.get(Location, edge.to_location_id)
                if destination is None or destination.type != "genesis_field" or not destination.genesis_site:
                    continue
                address = destination.genesis_site["cell"]
                if selector(42, address, records, version=VERSION_V2) is not None:
                    continue
                point = SurfacePoint(*destination.genesis_site["point"])
                try:
                    envrow = materialize_environment_point(fixture, cid, point)
                except (ValueError, RuntimeError):
                    continue
                facts = envrow.baseline
                sea = campaign_row.playable_state["territory"]["world_config"].get("sea_level_m", 0)
                if "EV-BIO-SEMIARIDO_ARBUSTIVO" not in set(facts.get("flora_contract", {}).get("eligible_habitat_ids", [])):
                    continue
                for archetype in ("EV-LOC-0236",):
                    accepted, status, reason = eligibility(archetype, facts, sea)
                    if accepted and status == "accepted":
                        choices.append((destination, edge, point, facts, archetype, reason))
                        break
                if choices:
                    break
            if not choices:
                raise RuntimeError("No adjacent active TP1 cell has real evidence for EV-LOC-0037 or EV-LOC-0051")
            destination, first_edge, fixture_point, fixture_facts, archetype, evidence_reason = choices[0]
            fixture_address = destination.genesis_site["cell"]

            # Test-process-only controlled selector and size hash. Candidate
            # eligibility still uses the actual materialized E1 evidence above.
            wgs2_families.candidate = lambda seed, address, records, **kw: (
                archetype if seed == 42 and address == fixture_address else None)
            original_hash = local_formations._hash
            def controlled_hash(seed, key, label, version=local_formations.VERSION):
                if label == "grau_abrigado":
                    return 2
                if label == "horizontal_span" and version == VERSION_V2:
                    scale = catalog()["EV-LOC-0236"]["geometria"]["escala_horizontal_m_sugerida"]
                    maximum = min(3400, int(scale["max"]))
                    minimum = min(maximum, int(scale["min"]))
                    return maximum-minimum
                return original_hash(seed, key, label, version)
            local_formations._hash = controlled_hash
            try:
                prepare_site(fixture, destination)
            finally:
                wgs2_families.candidate = original_selector
                local_formations._hash = original_hash
            fixture.flush()
            instance = (fixture.query(GenesisNaturalFormation)
                .filter_by(campaign_id=cid, generator_version=VERSION_V2,
                           archetype_id=archetype).one())
            initial_coverage = (fixture.query(GenesisFormationCoverageCell)
                .filter_by(campaign_id=cid, formation_id=instance.id).all())
            if len(initial_coverage) < 2:
                raise RuntimeError("Controlled v24 fixture did not span multiple cells")
            initial_stable_key = instance.stable_key
            instance_id = instance.id
            formation_location_id = instance.location_id
            first_exterior_id = destination.id
            initial_dimensions = dict(instance.data["dimensions"])
            initial_checksum = initial_coverage[0].contract_checksum
            micro_contract = instance.data.get("microenvironment", {})
            if micro_contract.get("status") != "active":
                raise RuntimeError(f"EV-LOC-0236 microenvironment is not active: {micro_contract!r}")
            from app.game.world.genesis.vegetation.service import context as vegetation_context, query_community, eligibility_at, materialize_individual
            from app.game.world.genesis.vegetation.microhabitat import resolve as resolve_microhabitat
            sampler = vegetation_context(fixture, cid)
            local_lookup_started=time.perf_counter()
            local_context = resolve_microhabitat(fixture, cid, fixture_point)
            local_lookup_seconds=time.perf_counter()-local_lookup_started
            if local_context is None:
                raise RuntimeError("Persisted coverage did not resolve its active microhabitat")
            community_query_started=time.perf_counter()
            local_community = query_community(fixture, cid, fixture_point)
            community_query_seconds=time.perf_counter()-community_query_started
            outside_point = local_formations._surface_offset(fixture_point,
                campaign_row.playable_state["territory"]["world_config"]["radius_m"], metres=5000)
            outside_context = resolve_microhabitat(fixture, cid, outside_point)
            if outside_context is not None:
                raise RuntimeError("A point outside the formation influence resolved a local modifier")
            local_sample = sampler.sample(fixture_point, microenvironment=local_context)
            outside_sample = sampler.sample(outside_point)
            test_species = sampler.catalog.species["EV-FL-1506"]
            local_species_state = eligibility_at(fixture, cid, sampler, test_species, fixture_point)
            outside_species_state = eligibility_at(fixture, cid, sampler, test_species, outside_point)
            founder = None
            founder_failure = None
            for population in sorted(local_community["populations"], key=lambda p: (-p["cover_ppm"], p["species_id"])):
                if population["founder_count"] <= 0:
                    continue
                try:
                    founder = materialize_individual(fixture, cid, fixture_point,
                        population["species_id"], 0, _sampler=sampler)
                    break
                except ValueError as exc:
                    founder_failure = str(exc)
            if founder is None:
                raise RuntimeError(f"No valid individual slot in the established local community: {founder_failure}")
            founder_id = founder.individual_id
            founder_species = founder.baseline["species_id"]
            founder_micro_signature = founder.baseline.get("microenvironment_context",{}).get("contract_signature")
            fixture.commit()

            action_index = 0
            def action(text, formation=None):
                nonlocal action_index
                action_index += 1
                body = {"text":text, "action_key":f"wgs2-221-{action_index}"}
                if formation:
                    body["formation_action"] = {"kind":formation}
                return request(prefix + "/actions" + query, body)

            def move(direction):
                result = action("Vou para " + direction + ".")
                if "cansado demais" not in result.get("mechanical_summary", "").casefold():
                    return result
                action("Eu descanso.")
                return action("Vou para " + direction + ".")

            # Observe the adjacent route, enter the field through TP1, then
            # reach the canonical formation using the generated local edge.
            observed_root = action("Olho ao redor.")
            if first_edge.direction and first_edge.direction.casefold() not in observed_root.get("mechanical_summary", "").casefold():
                raise AssertionError("The first TP1 route was not exposed by ordinary observation")
            entered_field = move(first_edge.direction)
            if entered_field["state"]["location"]["id"] != destination.id:
                raise AssertionError("First route did not traverse the selected TP1 edge")
            observed_field = action("Olho ao redor.")
            formation_edge = (fixture.query(LocationConnection)
                .filter_by(from_location_id=destination.id, to_location_id=instance.location_id, active=True).one())
            if formation_edge.direction and formation_edge.direction.casefold() not in observed_field.get("mechanical_summary", "").casefold():
                raise AssertionError("Local formation access was not exposed after observation")
            first_visit = move(formation_edge.direction)
            if first_visit["state"]["location"]["id"] != instance.location_id:
                raise AssertionError("First local access did not reach canonical formation Location")
            first_inspection = action("Inspeciono a formação.", "inspect")
            first_observation = action("Olho ao redor na depressão.")
            if "Sombra local" not in first_observation.get("mechanical_summary", ""):
                raise AssertionError("The visited WGS2.3 formation did not expose its supported shade fact")
            formation_id_first = first_visit["state"]["location"]["id"]
            if formation_id_first != formation_location_id:
                raise AssertionError("The first access did not resolve to the fixture's canonical formation")
            move("exterior")

            # Select a covered TP1 neighbor with no independent WGS2 candidate.
            covered_tokens = {(r.face,r.level,r.x,r.y) for r in initial_coverage}
            second_options = []
            for direction in DIRECTIONS:
                key = neighbor(CellKey(**fixture_address), direction)
                token = (key.face,key.level,key.x,key.y)
                if token == (root_key.face,root_key.level,root_key.x,root_key.y) or token not in covered_tokens:
                    continue
                if selector(42, vars(key), records, version=VERSION_V2) is not None:
                    continue
                edges = (fixture.query(LocationConnection)
                    .join(Location, Location.id == LocationConnection.to_location_id)
                    .filter(LocationConnection.from_location_id == destination.id,
                            LocationConnection.active.is_(True), Location.type == "genesis_field")
                    .all())
                match = next((e for e in edges if CellKey(**fixture.get(
                    Location, e.to_location_id).genesis_site["cell"]) == key), None)
                if match is not None:
                    second_options.append((key, match))
            if not second_options:
                raise RuntimeError("The controlled footprint has no adjacent, active, candidate-free covered cell")
            second_key, second_edge = second_options[0]
            second_move_started=time.perf_counter()
            second_field = move(second_edge.direction)
            second_cell_move_seconds=time.perf_counter()-second_move_started
            second_field_id = second_field["state"]["location"]["id"]
            fixture.expire_all()
            access_row = (fixture.query(GenesisFormationCoverageCell)
                .filter_by(campaign_id=cid, formation_id=instance.id, face=second_key.face,
                           level=second_key.level, x=second_key.x, y=second_key.y).one())
            second_access_id = access_row.access_location_id
            if not second_access_id or second_access_id == instance.location_id:
                raise AssertionError("Second covered cell did not materialize a distinct local access")
            access_edge = (fixture.query(LocationConnection)
                .filter_by(from_location_id=second_field_id, to_location_id=second_access_id, active=True).one())
            access_contract = access_edge.spatial_contract
            if (access_contract.get("version") != "WGS2_COVERAGE_ACCESS_V2"
                or access_contract.get("selection_policy") != "wgs2-overlap-priority-stable-key-r2"
                or access_contract.get("distance_m") != 10):
                raise AssertionError("Second access does not use the local spatial contract")
            second_observation = action("Olho ao redor.")
            if access_edge.direction.casefold() not in second_observation.get("mechanical_summary", "").casefold():
                raise AssertionError("Second access was not revealed by ordinary observation")
            second_access_started=time.perf_counter()
            second_visit = move(access_edge.direction)
            second_access_visit_seconds=time.perf_counter()-second_access_started
            if second_visit["state"]["location"]["id"] != second_access_id:
                raise AssertionError("Second local route did not reach the covered-cell access: " +
                    second_visit.get("mechanical_summary", "no movement summary"))
            second_inspection = action("Inspeciono a mesma formação no segundo ponto.", "inspect")
            persisted_instance = fixture.query(GenesisNaturalFormation).filter_by(
                campaign_id=cid, stable_key=initial_stable_key).one()
            if persisted_instance.id != instance.id or second_inspection.get("formation_result") is None:
                raise AssertionError("Second inspection did not resolve the original formation")
            same_physical_id = (fixture.query(GenesisNaturalFormation)
                .filter_by(campaign_id=cid, location_id=second_access_id).count() == 0)
            if not same_physical_id:
                raise AssertionError("A duplicate formation instance was created for the second access")
            coverage_before_restart = fixture.query(GenesisFormationCoverageCell).filter_by(
                campaign_id=cid, formation_id=instance.id).order_by(
                    GenesisFormationCoverageCell.face, GenesisFormationCoverageCell.level,
                    GenesisFormationCoverageCell.x, GenesisFormationCoverageCell.y).all()
            coverage_addresses = [(r.face,r.level,r.x,r.y) for r in coverage_before_restart]
            access_ids_before = sorted(r.access_location_id for r in coverage_before_restart if r.access_location_id)
            discovery_ids = {r.location_id for r in fixture.query(CharacterLocationDiscovery).filter_by(
                character_id=aid).all()}
            if instance.location_id not in discovery_ids or second_access_id not in discovery_ids:
                raise AssertionError("Both formation locations must be discovered by normal arrivals")
            from app.game.world.genesis.territory import validate_travel
            validate_travel(fixture, cid, access_edge)
            from app.game.world.genesis.sphere_metric import distance_m
            from app.game.world.genesis.sphere_config import parse_config
            config = parse_config(campaign_row.playable_state["territory"]["world_config"])
            anchors = [fixture.get(LocationSpatialAnchor, loc_id) for loc_id in
                       (second_field_id, second_access_id)]
            access_distance_m = distance_m(config, SurfacePoint(*anchors[0].point), SurfacePoint(*anchors[1].point))
            if not 9.5 <= access_distance_m <= 10.5:
                raise AssertionError(f"Second local access is not a 10 m walk: {access_distance_m}")
            fixture.commit()
        finally:
            fixture.close()

        map_before = request(prefix + "/map-view" + query)
        if _has_hidden_coords(map_before):
            raise AssertionError("Public map exposed hidden spatial coordinates")
        process.terminate(); process.wait(timeout=30)
        process = launch()
        resumed = request(prefix + "/start" + query, {})
        if resumed["state"]["location"]["id"] != second_access_id:
            raise AssertionError("Character location changed across backend restart")
        revisit_started=time.perf_counter()
        revisit = request(prefix + "/actions" + query, {"text":"Inspeciono após reiniciar.",
            "action_key":"wgs2-221-restart-inspect", "formation_action":{"kind":"inspect"}})
        resumed_observation = request(prefix + "/actions" + query, {"text":"Olho ao redor após reiniciar.",
            "action_key":"wgs2-23-restart-observe"})
        revisit_seconds=time.perf_counter()-revisit_started
        map_after = request(prefix + "/map-view" + query)
        if map_before != map_after or _has_hidden_coords(map_after):
            raise AssertionError("Map/discovery changed or exposed unknown coordinates after restart")
        with SessionLocal() as db:
            formations = db.query(GenesisNaturalFormation).filter_by(campaign_id=cid,
                stable_key=initial_stable_key).all()
            if len(formations) != 1 or formations[0].id != instance_id:
                raise AssertionError("Formation identity duplicated or changed after restart")
            rows = db.query(GenesisFormationCoverageCell).filter_by(campaign_id=cid,
                formation_id=instance_id).order_by(GenesisFormationCoverageCell.face,
                GenesisFormationCoverageCell.level,GenesisFormationCoverageCell.x,
                GenesisFormationCoverageCell.y).all()
            if [(r.face,r.level,r.x,r.y) for r in rows] != coverage_addresses:
                raise AssertionError("Coverage address set changed after restart")
            if any(r.contract_checksum != initial_checksum for r in rows):
                raise AssertionError("Coverage checksum changed after restart")
            if dict(formations[0].data["dimensions"]) != initial_dimensions:
                raise AssertionError("Formation dimensions changed after restart")
            if sorted(r.access_location_id for r in rows if r.access_location_id) != access_ids_before:
                raise AssertionError("Materialized access set changed after restart")
            if revisit.get("formation_result") is None:
                raise AssertionError("Formation cannot be inspected after restart")
            resumed_micro = resolve_microhabitat(db, cid, fixture_point)
            if resumed_micro is None or resumed_micro["contract_signature"] != local_context["contract_signature"]:
                raise AssertionError("Microhabitat signature did not persist across restart")
            resumed_founder = db.query(GenesisPlantIndividual).filter_by(campaign_id=cid,
                individual_id=founder_id).one_or_none()
            if resumed_founder is None or resumed_founder.baseline["species_id"] != founder_species:
                raise AssertionError("The established Vg2 individual did not persist across restart")
            discovery_after = {r.location_id for r in db.query(CharacterLocationDiscovery).filter_by(
                character_id=aid).all()}
            if not {formation_location_id, second_access_id} <= discovery_after:
                raise AssertionError("Formation discoveries were lost after restart")
            formations_before_delete = db.query(GenesisNaturalFormation).filter_by(campaign_id=cid).count()
            coverages_before_delete = db.query(GenesisFormationCoverageCell).filter_by(campaign_id=cid).count()

        req = Request(base + prefix, method="DELETE")
        with urlopen(req, timeout=60) as response:
            deleted = json.load(response)
        with SessionLocal() as db:
            remaining_formations = db.query(GenesisNaturalFormation).filter_by(campaign_id=cid).count()
            remaining_coverage = db.query(GenesisFormationCoverageCell).filter_by(campaign_id=cid).count()
        if not deleted.get("deleted") or remaining_formations or remaining_coverage:
            raise AssertionError("Explicit campaign deletion left formation coverage rows")
        report = {
            "classification":"PERCURSO HTTP CONTROLADO; formação WGS2 preparada com E1/T1/JR1 reais; origem vegetal controlada, não ocorrência orgânica",
            "profile":"world_genesis_ap1_tp1_wgs2_v3", "seed":42, "archetype":archetype,
            "catalog_record":"v24", "evidence_reason":evidence_reason,
            "start_seconds":round(start_seconds,3), "horizontal_span_m":initial_dimensions["horizontal_span_m"],
            "first_cell":vars(CellKey(**fixture_address)), "second_cell":vars(second_key),
            "coverage_cells":len(coverage_addresses), "coverage_faces":sorted({row[0] for row in coverage_addresses}),
            "first_exterior_location_id":first_exterior_id, "first_access_location_id":formation_location_id,
            "second_exterior_location_id":second_field_id, "second_access_location_id":second_access_id,
            "first_and_second_same_formation":persisted_instance.id == instance_id,
            "second_access_distance_m":round(access_distance_m,3),
            "http_action_seconds":{"second_cell_move_and_prepare":round(second_cell_move_seconds,3),
                "second_access_visit":round(second_access_visit_seconds,3),
                "restart_reinspection":round(revisit_seconds,3)},
            "first_inspection":bool(first_inspection.get("formation_result")),
            "second_inspection":bool(second_inspection.get("formation_result")),
            "restart_inspection":bool(revisit.get("formation_result")),
            "coverage_checksum":initial_checksum,
            "formation_count_before_delete":formations_before_delete,
            "coverage_count_before_delete":coverages_before_delete,
            "formation_count_after_delete":remaining_formations,
            "coverage_count_after_delete":remaining_coverage,
            "restart_preserved_location_dimensions_discoveries_and_map":True,
            "microenvironment_status":micro_contract["status"],
            "microenvironment_features":micro_contract["features"],
            "microenvironment_contract_signature":micro_contract["signature"],
            "local_eligibility_context_resolved":bool(local_context),
            "outside_eligibility_context":outside_context,
            "local_community_persisted":bool(local_community.get("persisted")),
            "local_community_established":bool(local_community.get("established")),
            "local_community_dominant_species":local_community.get("dominant_species"),
            "individual_id":founder_id,
            "individual_species_id":founder_species,
            "individual_alive_after_restart":bool(resumed_founder.state["alive"]),
            "individual_microenvironment_signature":founder_micro_signature,
            "local_lookup_seconds":round(local_lookup_seconds,6),
            "local_community_query_seconds":round(community_query_seconds,6),
            "EV-FL-1506_actual_local_state":local_species_state[0],
            "EV-FL-1506_actual_local_reasons":local_species_state[1],
            "EV-FL-1506_actual_outside_state":outside_species_state[0],
            "EV-FL-1506_actual_outside_reasons":outside_species_state[1],
            "local_sample_P_over_PET":local_sample.get("source_evidence",{}).get("P_over_PET"),
            "outside_sample_P_over_PET":outside_sample.get("source_evidence",{}).get("P_over_PET"),
            "local_sample_context_signature":local_sample.get("microenvironment_context",{}).get("contract_signature"),
            "outside_sample_has_no_local_context":outside_sample.get("microenvironment_context") is None,
            "gameplay_observation_reports_shade":"Sombra local" in first_observation.get("mechanical_summary", ""),
            "public_map_coordinate_leaks":False,
            "temporary_database":str(dbpath),
        }
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        process.terminate(); process.wait(timeout=30); log.close()
        current_hash = hashlib.sha256(main_db.read_bytes()).hexdigest() if main_db.exists() else None
        if current_hash != main_hash:
            raise AssertionError("Main database changed during isolated WGS2.2.1 playtest")


def _has_hidden_coords(value):
    if isinstance(value, dict):
        return any(key in {"genesis_site","spatial_contract","from_point","to_point","physical_point"}
                   or _has_hidden_coords(item) for key,item in value.items())
    if isinstance(value,list):
        return any(_has_hidden_coords(item) for item in value)
    return False


if __name__ == "__main__":
    main()
