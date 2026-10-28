"""Real-HTTP WGS2 v2 smoke exploration, isolated in temporary SQLite."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.game.world.genesis.wgs2_families import candidate as _wgs2_candidate, VERSION_V2
from app.game.world.genesis.local_formations import catalog
def candidate_v2(seed, address):
    return _wgs2_candidate(seed, address, catalog(), version=VERSION_V2)
from app.game.world.genesis.sphere_topology import CellKey, DIRECTIONS, SurfacePoint, neighbor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 0, 7, 2026, 12345])
    parser.add_argument("--max-km", type=float, default=50)
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    main_db = backend / "everreach.db"
    protected_hash = hashlib.sha256(main_db.read_bytes()).hexdigest() if main_db.exists() else None
    folder = Path(tempfile.mkdtemp(prefix="everreach-wgs2-v2-playtest-"))
    dbpath = folder / "playtest.sqlite"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + dbpath.as_posix(), "PYTHONIOENCODING": "utf-8"}
    for role in ("INTENT", "NARRATIVE", "REGENERATION"):
        env[role + "_LLM_PROVIDER"] = "disabled"
        env[role + "_LLM_FALLBACK_PROVIDER"] = ""
        env[role + "_LLM_FALLBACK_MODEL"] = ""
    with (folder / "migration.log").open("w", encoding="utf-8") as log:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend,
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def request(path, body=None):
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(base + path, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=300) as response:
                return json.load(response)
        except HTTPError as exc:
            raise AssertionError(f"{path} {exc.code}: {exc.read().decode('utf-8')}") from exc

    server_log = (folder / "server.log").open("a", encoding="utf-8")

    def launch():
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                    "--port", str(port)], cwd=backend, env=env, stdout=server_log,
                                   stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(240):
            if process.poll() is not None:
                raise RuntimeError(f"Uvicorn exited; inspect {folder / 'server.log'}")
            try:
                request("/openapi.json")
                return process
            except OSError:
                time.sleep(0.25)
        process.terminate()
        process.wait()
        raise RuntimeError("Uvicorn startup timeout")

    report = {"profile": "world_genesis_ap1_tp1_wgs2_v2", "max_km": args.max_km,
              "seeds": [], "http_server": "real Uvicorn; LLM providers disabled",
              "database": "temporary SQLite; main DB hash checked unchanged"}
    process = launch()
    try:
        for seed in args.seeds:
            campaign = request("/api/campaigns", {"name": f"WGS2 v1 route {seed}",
                "world_profile": report["profile"], "world_seed": seed})
            cid = campaign["id"]
            actor = request(f"/api/campaigns/{cid}/characters", {"name": "Exploradora"})
            aid = actor["id"]
            prefix = f"/api/campaigns/{cid}"
            query = f"?character_id={aid}"
            action_number = 0

            def action(text, formation=None):
                nonlocal action_number
                action_number += 1
                body = {"text": text, "action_key": f"wgs2-v1-{seed}-{action_number}"}
                if formation:
                    body["formation_action"] = {"kind": formation}
                start = time.perf_counter()
                result = request(prefix + "/actions" + query, body)
                return result, time.perf_counter() - start

            started = time.perf_counter()
            start_response = request(prefix + "/start" + query, {})
            start_seconds = time.perf_counter() - started
            root_id = start_response["state"]["location"]["id"]
            with sqlite3.connect(dbpath) as con:
                root_site = json.loads(con.execute("select genesis_site from locations where id=?", (root_id,)).fetchone()[0])
                state = json.loads(con.execute("select playable_state from campaigns where id=?", (cid,)).fetchone()[0])
                assert state["natural_formations"].get("selection_policy") == "wgs2-family-opportunities-r1"
                radius_m = state["territory"]["world_config"]["radius_m"]
            root_cell = CellKey(**root_site["cell"])
            visited_cells = {tuple(root_site["cell"][k] for k in ("face", "level", "x", "y"))}
            explored_cell_ids = {root_id}
            raw_checked = {}
            checked_cells = set()
            route_metrics = Counter()
            path_location_ids = [start_response["state"]["location"]["id"]]
            last_formation_field_id = None
            last_inspection_result = None
            resume_location_id = start_response["state"]["location"]["id"]
            archetypes = Counter()
            signal_events = []
            signal_occurrences = []
            interaction_counts = Counter()
            discoveries_at_km = []
            discovered_forms = []
            known_discovery_ids = set()
            generation_seconds = []
            travel_seconds = []
            public_map_leaks = []

            # Mixed, seed-stable route style: early loop around spawn, then directional
            # legs with branches; every leg still follows an observed active TP1 edge.
            if seed == 42:
                preference = ["norte", "leste", "sul", "oeste", "nordeste", "sudeste", "sudoeste", "noroeste"]
            elif seed == 0:
                preference = ["leste", "nordeste", "sudeste", "norte", "sul", "oeste", "noroeste", "sudoeste"]
            elif seed == 7:
                preference = ["norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]
            elif seed == 2026:
                preference = ["sul", "oeste", "norte", "leste", "sudoeste", "noroeste", "nordeste", "sudeste"]
            else:
                preference = ["oeste", "sudoeste", "noroeste", "norte", "leste", "nordeste", "sudeste", "sul"]

            # Explore the start, then walk until the requested physical route distance.
            seen_signals = set()
            observed, elapsed = action("Olho ao redor.")
            generation_seconds.append(elapsed)
            initial_signals = _extract_signal_phrases(observed.get("mechanical_summary", ""))
            signal_events.extend(initial_signals)
            signal_occurrences.extend({"text":text,"distance_km":0.0,"world_minutes":_world_minutes(dbpath,cid)} for text in initial_signals)
            pending_directions = [d for text in initial_signals if (d := _signal_direction(text))]
            _sample_player_state(request, prefix, query, public_map_leaks, seed)
            _record_checked_candidates(dbpath, start_response["state"]["location"]["id"], seed, raw_checked, checked_cells)
            for row in _discovered_formations(dbpath, cid, aid):
                known_discovery_ids.add(row["location_id"])
                discovered_forms.append({"archetype":row["archetype_id"],"distance_km":0.0,
                    "world_minutes":_world_minutes(dbpath,cid)})
            if "indício próximo" in observed.get("mechanical_summary", "").casefold() or "indicio proximo" in observed.get("mechanical_summary", "").casefold():
                entered, elapsed = action("Vou para indício próximo.")
                travel_seconds.append(elapsed)
                if entered["state"]["location"].get("type") == "genesis_formation":
                    last_formation_field_id = root_id
                    route_metrics["distance_m"] += 10
                    inspect, elapsed = action("Inspeciono o local descoberto.", "inspect")
                    interaction_counts["inspections"] += int(bool(inspect.get("formation_result")))
                    interaction_counts["formation_visits"] += 1
                    formation = inspect.get("formation_result") or {}
                    last_inspection_result = formation
                    interacted, _elapsed = action("Examino a formaÃ§Ã£o que encontrei.", "interact")
                    interaction_counts["interactions"] += int(bool(interacted.get("formation_result")))
                    action("Olho ao redor.")
                    returned, elapsed = action("Vou para exterior.")
                    travel_seconds.append(elapsed)
                    if returned["state"]["location"]["id"] == root_id:
                        route_metrics["distance_m"] += 10
                    observed, elapsed = action("Olho ao redor.")
                    generation_seconds.append(elapsed)
                    pending_directions = [d for text in _extract_signal_phrases(observed.get("mechanical_summary", ""))
                        if (d := _signal_direction(text))]
            steps = 0
            while route_metrics["distance_m"] < args.max_km * 1000 and steps < 400:
                current = start_response["state"]["location"]["id"] if steps == 0 else current_id
                with sqlite3.connect(dbpath) as con:
                    edges = con.execute("""select e.id,e.to_location_id,e.direction,e.distance,l.genesis_site,l.type
                        from location_connections e join locations l on l.id=e.to_location_id
                        where e.from_location_id=? and e.active=1""", (current,)).fetchall()
                options = []
                for edge in edges:
                    if not edge[4] or edge[5] != "genesis_field":
                        continue
                    address = json.loads(edge[4]).get("cell")
                    if not address:
                        continue
                    token = tuple(address[k] for k in ("face", "level", "x", "y"))
                    if token in visited_cells:
                        continue
                    options.append((edge, token, address))
                if not options:
                    route_metrics["route_stopped_no_unvisited_active_tp1_edge"] += 1
                    break
                # Rotate the tie-break order to avoid following a single compass ray.
                shift = (steps // 3 + seed) % len(preference)
                prefs = preference[shift:] + preference[:shift]
                preferred_signal = pending_directions[0] if pending_directions else None
                if preferred_signal and not any(item[0][2] == preferred_signal for item in options):
                    pending_directions.clear()
                    preferred_signal = None
                options.sort(key=lambda item: (0 if item[0][2] == preferred_signal else 1,
                    prefs.index(item[0][2]) if item[0][2] in prefs else len(prefs), item[1]))
                edge, token, address = options[0]
                if edge[2] == preferred_signal:
                    pending_directions.pop(0)
                moved, elapsed = action("Vou para " + edge[2] + ".")
                travel_seconds.append(elapsed)
                if moved["state"]["location"]["id"] != edge[1]:
                    failure = moved.get("mechanical_summary", "").casefold()
                    if "cansado demais" in failure:
                        rested, elapsed = action("Eu descanso.")
                        generation_seconds.append(elapsed)
                        route_metrics["rests"] += 1
                        if rested["state"]["location"]["id"] == current:
                            moved, elapsed = action("Vou para " + edge[2] + ".")
                            travel_seconds.append(elapsed)
                    if moved["state"]["location"]["id"] != edge[1]:
                        route_metrics["movement_rejections"] += 1
                        route_metrics["movement_stop_reason"] = moved.get("mechanical_summary", "unknown")
                        break
                current_id = edge[1]
                path_location_ids.append(current_id)
                explored_cell_ids.add(current_id)
                visited_cells.add(token)
                route_metrics["moves"] += 1
                route_metrics["distance_m"] += float(edge[3] or 0) * 1000
                route_metrics["time_minutes"] = _world_minutes(dbpath, cid)
                observed, elapsed = action("Olho ao redor.")
                generation_seconds.append(elapsed)
                _record_checked_candidates(dbpath, current_id, seed, raw_checked, checked_cells)
                phrases = _extract_signal_phrases(observed.get("mechanical_summary", ""))
                signal_occurrences.extend({"text":text,"distance_km":round(route_metrics["distance_m"]/1000,3),
                    "world_minutes":_world_minutes(dbpath,cid)} for text in phrases)
                for phrase in phrases:
                    if phrase not in seen_signals:
                        signal_events.append(phrase)
                        seen_signals.add(phrase)
                pending_directions = [d for text in phrases if (d := _signal_direction(text))]
                if phrases:
                    clue_map=request(prefix + "/map-view" + query)
                    unknown=_unknown_formation_ids(dbpath,cid,aid,clue_map)
                    if unknown:
                        public_map_leaks.append("unknown_formation_ids:"+",".join(unknown))
                summary = observed.get("mechanical_summary", "")
                if "indício próximo" in summary.casefold() or "indicio proximo" in summary.casefold():
                    entered, elapsed = action("Vou para indício próximo.")
                    travel_seconds.append(elapsed)
                    last_formation_field_id = current_id
                    inspect, elapsed = action("Inspeciono o local descoberto.", "inspect")
                    interaction_counts["inspections"] += int(bool(inspect.get("formation_result")))
                    interaction_counts["formation_visits"] += int(entered["state"]["location"].get("type") == "genesis_formation")
                    if entered["state"]["location"].get("type") == "genesis_formation":
                        route_metrics["distance_m"] += 10
                    formation = inspect.get("formation_result") or {}
                    last_inspection_result = formation
                    interacted, elapsed = action("Examino a formação que encontrei.", "interact")
                    interaction_counts["interactions"] += int(bool(interacted.get("formation_result")))
                    if formation.get("water"):
                        # The public action response intentionally strips the
                        # formation instance id. Correlate only inside the
                        # temporary test DB through the visited interior.
                        formation_location_id = entered["state"]["location"]["id"]
                        with sqlite3.connect(dbpath) as con:
                            after_water = con.execute("""select w.stored_litres,w.revision
                                from genesis_local_water_bodies w
                                join genesis_natural_formations f on f.id=w.formation_id
                                where f.location_id=?""", (formation_location_id,)).fetchone()
                        if after_water != (formation["water"]["stored_litres"], 0):
                            raise AssertionError("Inspection/interact changed the finite spring stock")
                        interaction_counts["water_interactions_without_transfer"] += 1
                    if formation.get("archetype_id") in ("EV-LOC-0049", "EV-LOC-0050", "EV-LOC-0051"):
                        action("Olho ao redor.")
                        inside, elapsed = action("Vou para entrar.")
                        travel_seconds.append(elapsed)
                        if inside["state"]["location"].get("type") == "genesis_formation_interior":
                            interaction_counts["cavity_entries"] += 1
                            action("Inspeciono o interior.", "inspect")
                            action("Olho ao redor.")
                            outside, elapsed = action("Vou para sair.")
                            travel_seconds.append(elapsed)
                            interaction_counts["cavity_returns"] += int(outside["state"]["location"].get("type") == "genesis_formation")
                    action("Olho ao redor.")
                    returned, elapsed = action("Vou para exterior.")
                    travel_seconds.append(elapsed)
                    interaction_counts["successful_returns"] += int(returned["state"]["location"]["id"] == current_id)
                    if returned["state"]["location"]["id"] == current_id:
                        route_metrics["distance_m"] += 10
                current_discoveries = _discovered_formations(dbpath, cid, aid)
                for row in current_discoveries:
                    if row["location_id"] not in known_discovery_ids:
                        known_discovery_ids.add(row["location_id"])
                        discovered_forms.append({"archetype": row["archetype_id"],
                            "distance_km": round(route_metrics["distance_m"] / 1000, 3),
                            "world_minutes": _world_minutes(dbpath, cid)})
                with sqlite3.connect(dbpath) as con:
                    site_text = con.execute("select genesis_site from locations where id=?", (current_id,)).fetchone()[0]
                current_site = json.loads(site_text or "{}")
                current_address = current_site.get("cell")
                if current_address:
                    selected = candidate_v2(seed, current_address)
                    if selected:
                        raw_checked[tuple(current_address[k] for k in ("face", "level", "x", "y"))] = selected
                        archetypes[selected] += 1
                thresholds = (5, 10, 20, 50)
                for threshold in thresholds:
                    if route_metrics["distance_m"] >= threshold * 1000 and not any(x["km"] == threshold for x in discoveries_at_km):
                        discoveries_at_km.append({"km": threshold, "snapshot": _funnel_snapshot(
                            dbpath, cid, aid, explored_cell_ids, raw_checked, interaction_counts["inspections"], checked_cells)})
                steps += 1
            exploration_distance_km = round(route_metrics["distance_m"] / 1000, 3)
            if last_formation_field_id in path_location_ids:
                target_index = path_location_ids.index(last_formation_field_id)
                for target_id in reversed(path_location_ids[target_index:-1]):
                    action("Olho ao redor.")
                    with sqlite3.connect(dbpath) as con:
                        edge = con.execute("select direction,distance from location_connections where from_location_id=? and to_location_id=? and active=1",
                                           (current_id, target_id)).fetchone()
                    if edge is None:
                        break
                    returned, elapsed = action("Vou para " + edge[0] + ".")
                    travel_seconds.append(elapsed)
                    if returned["state"]["location"]["id"] != target_id and "cansado demais" in returned.get("mechanical_summary", "").casefold():
                        action("Eu descanso.")
                        returned, elapsed = action("Vou para " + edge[0] + ".")
                        travel_seconds.append(elapsed)
                    if returned["state"]["location"]["id"] != target_id:
                        break
                    route_metrics["distance_m"] += float(edge[1] or 0) * 1000
                    current_id = target_id
                if current_id == last_formation_field_id:
                    observed, _elapsed = action("Olho ao redor.")
                    summary = observed.get("mechanical_summary", "").casefold()
                    if "indício próximo" in summary or "indicio proximo" in summary:
                        entered = action("Vou para indício próximo.")[0]
                        if entered["state"]["location"].get("type") == "genesis_formation":
                            resume_location_id = entered["state"]["location"]["id"]
                            revisit = action("Inspeciono novamente o local.", "inspect")[0]
                            if revisit.get("formation_result"):
                                last_inspection_result = revisit["formation_result"]
            # A real replayable map is checked at the end; private formation IDs and
            # physical anchors must not occur in this public route payload.
            public_map = request(prefix + "/map-view" + query)
            if _map_contains_hidden_spatial_fields(public_map):
                public_map_leaks.append("hidden_spatial_fields")
            final = _funnel_snapshot(dbpath, cid, aid, explored_cell_ids, raw_checked,
                                     interaction_counts["inspections"], checked_cells)
            report["seeds"].append({
                "seed": seed, "campaign_id": cid, "start_seconds": round(start_seconds, 3),
                "route_strategy": "seed-stable 2D path; active TP1 edges only; follows public, direction-only geographic clues",
                "visited_cells": len(explored_cell_ids), "exploration_distance_km": exploration_distance_km,
                "route_distance_including_revisit_km": round(route_metrics["distance_m"] / 1000, 3),
                "world_elapsed_minutes": _world_minutes(dbpath, cid), "moves": route_metrics["moves"],
                "rests": route_metrics["rests"],
                "movement_stop_reason": route_metrics.get("movement_stop_reason"),
                "cells_checked_including_adjacent": len(checked_cells),
                "raw_candidates_checked": len(raw_checked), "raw_archetypes": dict(Counter(raw_checked.values())),
                "context_decisions": final["context_decisions"], "materialized": final["materialized"],
                "rejection_reasons": final["rejection_reasons"],
                "discovered": final["discovered"], "reachable_from_visited_cells": final["reachable_from_visited_cells"],
                "visited_formations": final["visited_formations"], "inspections": final["inspections"],
                "discovery_spacing": _spacing(discovered_forms), "discovered_formations": discovered_forms,
                "http_interactions": dict(interaction_counts),
                "signals": signal_events, "threshold_snapshots": discoveries_at_km,
                "signal_occurrences": signal_occurrences,
                "mean_generation_http_seconds": round(sum(generation_seconds) / max(1, len(generation_seconds)), 3),
                "mean_travel_http_seconds": round(sum(travel_seconds) / max(1, len(travel_seconds)), 3),
                "public_map_hidden_coordinate_leaks": public_map_leaks,
                "max_candidate_probe_bound_per_observation": 4,
            })
            if seed == args.seeds[0]:
                before_restart = request(prefix + "/map-view" + query)
                with sqlite3.connect(dbpath) as con:
                    previous_location = con.execute("select location_id from characters where id=?", (aid,)).fetchone()[0]
                process.terminate()
                process.wait(timeout=30)
                process = launch()
                resumed = request(prefix + "/start" + query, {})
                after_restart = request(prefix + "/map-view" + query)
                if resumed["state"]["location"]["id"] != previous_location or before_restart != after_restart:
                    raise AssertionError("WGS2 v2 location/map state changed after backend restart")
                persisted_inspection = None
                if last_inspection_result and resumed["state"]["location"].get("type") != "genesis_formation":
                    look_after_restart = action("Olho ao redor.")[0]
                    if "indício próximo" in look_after_restart.get("mechanical_summary", "").casefold() or "indicio proximo" in look_after_restart.get("mechanical_summary", "").casefold():
                        entered_after_restart = action("Vou para indício próximo.")[0]
                        if entered_after_restart["state"]["location"].get("type") == "genesis_formation":
                            persisted_inspection = action("Inspeciono após reinício.", "inspect")[0].get("formation_result")
                elif last_inspection_result:
                    persisted_inspection = action("Inspeciono após reinício.", "inspect")[0].get("formation_result")
                if last_inspection_result and persisted_inspection is not None:
                    if persisted_inspection != last_inspection_result:
                        raise AssertionError("WGS2 v2 formation inspection changed after backend restart")
                report["seeds"][-1]["restart_persistence"] = {
                    "same_location": True, "same_public_map": True,
                    "revisit_inspection_after_restart": bool(persisted_inspection),
                }
            print(seed, json.dumps(report["seeds"][-1], ensure_ascii=False), flush=True)
    finally:
        process.terminate()
        process.wait(timeout=30)
        server_log.close()
        current_hash = hashlib.sha256(main_db.read_bytes()).hexdigest() if main_db.exists() else None
        if protected_hash != current_hash:
            raise AssertionError("Main DB changed during isolated playtest")
        report["temporary_database"] = str(dbpath)
        report["main_database_unchanged"] = True
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(folder / "report.json"), "database": str(dbpath),
                          "main_database_unchanged": True}, indent=2), flush=True)


def _world_minutes(path, campaign_id):
    with sqlite3.connect(path) as con:
        row = con.execute("select year,month,day,hour,minute from world_times where campaign_id=?", (campaign_id,)).fetchone()
    if row is None:
        return 0
    year, month, day, hour, minute = row
    return ((((year - 1) * 12 + month - 1) * 30 + day - 1) * 24 + hour) * 60 + minute


def _record_checked_candidates(path, current_location_id, seed, raw_checked, checked_cells):
    with sqlite3.connect(path) as con:
        rows = con.execute("""select l.genesis_site from location_connections e join locations l on l.id=e.to_location_id
            where e.from_location_id=? and e.active=1 and l.type='genesis_field'""", (current_location_id,)).fetchall()
        current = con.execute("select genesis_site from locations where id=?", (current_location_id,)).fetchone()
    sites = [json.loads(row[0]) for row in rows if row[0]]
    if current and current[0]:
        sites.append(json.loads(current[0]))
    for site in sites:
        address = (site or {}).get("cell")
        if not address:
            continue
        key = tuple(address[k] for k in ("face", "level", "x", "y"))
        checked_cells.add(key)
        candidate = candidate_v2(seed, address)
        if candidate:
            raw_checked[key] = candidate


def _funnel_snapshot(path, campaign_id, character_id, visited_location_ids, raw_checked,
                     inspection_count=0, checked_cells=None):
    with sqlite3.connect(path) as con:
        rows = con.execute("select id,location_id,archetype_id from genesis_natural_formations where campaign_id=?", (campaign_id,)).fetchall()
        decisions = con.execute("select status,archetype_id,decision from genesis_formation_candidates where campaign_id=?", (campaign_id,)).fetchall()
        discovered = {r[0] for r in con.execute("select location_id from character_location_discoveries where character_id=?", (character_id,))}
        visited = {r[0] for r in con.execute("select location_id from character_location_discoveries where character_id=? and status='VISITED'", (character_id,))}
        active_access = con.execute("""select count(*) from location_connections e join genesis_natural_formations f
              on e.to_location_id=f.location_id where f.campaign_id=? and e.active=1
              and e.from_location_id in (%s)""" % (','.join('?' for _ in visited_location_ids) or "NULL"),
              (campaign_id, *sorted(visited_location_ids))).fetchone()[0]
        environment_points=con.execute("select count(*) from genesis_environment_points where campaign_id=?",(campaign_id,)).fetchone()[0]
        campaign_locations=con.execute("select count(*) from locations where region_id in (select id from regions where campaign_id=?)",(campaign_id,)).fetchone()[0]
    return {"cells_checked": len(checked_cells or ()), "raw_candidates_checked": len(raw_checked),
        "context_decisions": dict(Counter(row[0] for row in decisions)),
        "rejection_reasons": dict(Counter(reason for status, _archetype, decision in decisions
            if status == "rejected" for reason in json.loads(decision).get("reasons", []))),
        "materialized": len(rows),
        "materialized_archetypes": dict(Counter(row[2] for row in rows)),
        "discovered": sum(row[1] in discovered for row in rows),
        "reachable_from_visited_cells": active_access,
        "visited_formations": sum(row[1] in visited for row in rows),
        "inspections": inspection_count,
        "persisted_environment_points": environment_points,
        "campaign_locations_including_tp1_stubs": campaign_locations}


def _extract_signal_phrases(summary):
    # Only public prose returned by the normal action flow is consumed here.
    marker = "Indícios geográficos próximos:"
    if marker not in summary:
        return []
    tail = summary.split(marker, 1)[1]
    tail = tail.split("Rotas perceptíveis:", 1)[0].split("Rotas perceptiveis:", 1)[0]
    return [part.strip() for part in tail.split(";") if part.strip()]


def _signal_direction(text):
    for direction in ("nordeste", "noroeste", "sudeste", "sudoeste", "norte", "sul", "leste", "oeste"):
        if text.rstrip(" .").casefold().endswith(" ao " + direction):
            return direction
    return None


def _discovered_formations(path, campaign_id, character_id):
    with sqlite3.connect(path) as con:
        rows = con.execute("""select f.location_id,f.archetype_id from genesis_natural_formations f
            join character_location_discoveries d on d.location_id=f.location_id
            where f.campaign_id=? and d.character_id=?""", (campaign_id, character_id)).fetchall()
    return [{"location_id": row[0], "archetype_id": row[1]} for row in rows]


def _spacing(records):
    values = sorted(row["distance_km"] for row in records)
    if len(values) < 2:
        return {"count": len(values), "between_discovery_km": []}
    return {"count": len(values), "between_discovery_km": [round(b - a, 3) for a, b in zip(values, values[1:])]}


def _map_contains_hidden_spatial_fields(value):
    if isinstance(value, dict):
        return any(key in {"genesis_site", "spatial_contract", "from_point", "to_point", "physical_point"}
                   or _map_contains_hidden_spatial_fields(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_map_contains_hidden_spatial_fields(item) for item in value)
    return False


def _unknown_formation_ids(path, campaign_id, character_id, public_map):
    public_ids={row.get("id") for row in public_map.get("locations", [])}
    with sqlite3.connect(path) as con:
        rows=con.execute("""select f.location_id from genesis_natural_formations f
            where f.campaign_id=? and not exists(select 1 from character_location_discoveries d
              where d.character_id=? and d.location_id=f.location_id)""",(campaign_id,character_id)).fetchall()
    return sorted(location_id for (location_id,) in rows if location_id in public_ids)


def _sample_player_state(request, prefix, query, leaks, seed):
    # The public map endpoint is the only observation surface used for discovery.
    payload = request(prefix + "/map-view" + query)
    if _map_contains_hidden_spatial_fields(payload):
        leaks.append(f"seed_{seed}:hidden_spatial_fields")


if __name__ == "__main__":
    main()
