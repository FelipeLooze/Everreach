"""Matched AP1/WGS1/WGS2 campaign-start profile in disposable SQLite."""
from __future__ import annotations

import json
import os
import ctypes
from ctypes import wintypes
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 2026])
    parser.add_argument("--profiles", nargs="+", default=["world_genesis_ap1_v1",
        "world_genesis_ap1_tp1_wgs1_v2", "world_genesis_ap1_tp1_wgs2_v1"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    root = backend.parent
    folder = Path(tempfile.mkdtemp(prefix="everreach-wgs2-perf-"))
    dbpath = folder / "profile.sqlite"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + dbpath.as_posix(), "PYTHONIOENCODING": "utf-8"}
    for role in ("INTENT", "NARRATIVE", "REGENERATION"):
        env[role + "_LLM_PROVIDER"] = "disabled"
        env[role + "_LLM_FALLBACK_PROVIDER"] = ""
        env[role + "_LLM_FALLBACK_MODEL"] = ""
    with (folder / "migrations.log").open("w", encoding="utf-8") as log:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend,
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    os.environ.update(env)

    sys.path.insert(0, str(backend))
    from sqlalchemy import event
    from app.db.database import engine

    sql = {"count": 0, "seconds": 0.0}
    def before(_conn, _cursor, _statement, _params, context, _many):
        context._wgs_started = time.perf_counter()
        sql["count"] += 1
    def after(_conn, _cursor, _statement, _params, context, _many):
        sql["seconds"] += time.perf_counter() - context._wgs_started
    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)

    import app.game.world.genesis.playable as playable
    from app.game.world.genesis import territory
    from app.game.world.genesis.vegetation import service as vegetation_service
    from app.game.world.genesis.environment import service as environment_service
    from app.game.world.genesis.vegetation import resources as vegetation_resources
    from app.game.world.genesis.vegetation import lifecycle as vegetation_lifecycle
    from app.game.world.genesis.vegetation import actions as vegetation_actions
    from app.game import game_state
    from app.api import serializers
    from app.ai import context_builder
    phases: dict[str, float] = {}
    def timed(obj, name, label=None):
        original = getattr(obj, name)
        key = label or name
        def wrapper(*a, **kw):
            started = time.perf_counter()
            try:
                return original(*a, **kw)
            finally:
                phases[key] = phases.get(key, 0.0) + time.perf_counter() - started
        setattr(obj, name, wrapper)

    for name in ("initialize_world", "initialize_terrain", "initialize_hydrology",
                 "initialize_regional_hydrology", "initialize_climate", "initialize_water_balance",
                 "initialize_geometry", "initialize_reconciliation", "initialize_practical_hydrology",
                 "initialize_geology", "initialize_regional_geology", "initialize_environment",
                 "find_start", "materialize_sector"):
        timed(playable, name)
    for name, label in (("initialize_vegetation", "initialize_vegetation"),
                        ("initialize_resources", "initialize_resources"),
                        ("initialize_life", "initialize_life"), ("initialize_ga2", "initialize_ga2")):
        obj = playable.vegetation if name == "initialize_vegetation" else (
            playable.resources if name == "initialize_resources" else
            playable.lifecycle if name == "initialize_life" else playable)
        timed(obj, name, label)
    timed(territory, "initialize_territory")
    for obj, name in ((vegetation_service, "context"),
                      (vegetation_service, "materialize_community"),
                      (vegetation_service, "materialize_individual"),
                      (environment_service, "materialize_environment_point"),
                      (environment_service, "query_environment"),
                      (vegetation_resources, "available_now"),
                      (vegetation_lifecycle, "phase_available")):
        timed(obj, name)
    for obj, name in ((vegetation_actions, "encounter"), (game_state, "build_game_state"),
                      (serializers, "to_game_state_response"), (context_builder, "build_context")):
        timed(obj, name)
    timed(playable, "narrate_facts")

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    if os.name == "nt":
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _psapi = ctypes.WinDLL("psapi", use_last_error=True)
        _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        _get_memory = _psapi.GetProcessMemoryInfo
        _get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        _get_memory.restype = wintypes.BOOL
    def memory_sample():
        if os.name != "nt":
            try:
                import psutil
                info = psutil.Process(os.getpid()).memory_info()
                return {"working_set_bytes": info.rss, "peak_working_set_bytes": None}
            except ImportError:
                return {"working_set_bytes": None, "peak_working_set_bytes": None}
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        ok = _get_memory(_kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        if not ok:
            return {"working_set_bytes": None, "peak_working_set_bytes": None}
        return {"working_set_bytes": counters.WorkingSetSize,
                "peak_working_set_bytes": counters.PeakWorkingSetSize}
    memory_start = memory_sample()

    from fastapi.testclient import TestClient
    from app.main import app
    profiles = args.profiles
    results = []
    with TestClient(app) as client:
        for profile in profiles:
            for seed in args.seeds:
                phases.clear()
                sql_start = dict(sql)
                campaign_start = time.perf_counter()
                c = client.post("/api/campaigns", json={"name": f"Perf {profile} {seed}",
                    "world_profile": profile, "world_seed": seed})
                c.raise_for_status()
                campaign = c.json()
                campaign_elapsed = time.perf_counter() - campaign_start
                character_start = time.perf_counter()
                a = client.post(f"/api/campaigns/{campaign['id']}/characters", json={"name": "Perf"})
                a.raise_for_status()
                actor = a.json()
                character_elapsed = time.perf_counter() - character_start
                start_start = time.perf_counter()
                start_cpu = time.process_time()
                s = client.post(f"/api/campaigns/{campaign['id']}/start",
                    params={"character_id": actor["id"]}, json={})
                s.raise_for_status()
                start_elapsed = time.perf_counter() - start_start
                start_cpu_seconds = time.process_time() - start_cpu
                memory_now = memory_sample()
                results.append({"profile": profile, "seed": seed,
                    "cold_or_warm": "cold_first_campaign" if len(results) == 0 else "warm_process",
                    "campaign_create_s": round(campaign_elapsed, 3),
                    "character_create_s": round(character_elapsed, 3),
                    "start_http_s": round(start_elapsed, 3),
                    "start_process_cpu_s": round(start_cpu_seconds, 3),
                    "phase_s": {k: round(v, 3) for k, v in phases.items()},
                    "sql_statements": sql["count"] - sql_start["count"],
                    "sql_execute_s": round(sql["seconds"] - sql_start["seconds"], 3),
                    "working_set_bytes_after_start": memory_now["working_set_bytes"],
                    "working_set_delta_bytes_from_process_start": (
                        memory_now["working_set_bytes"]-memory_start["working_set_bytes"]
                        if memory_now["working_set_bytes"] is not None and memory_start["working_set_bytes"] is not None else None),
                    "process_peak_working_set_bytes": memory_now["peak_working_set_bytes"],
                    "start_status": s.status_code})
                # A campaign stays isolated in the disposable database, but its seed/profile
                # results remain available for a later route smoke check in another harness.
    report = {"environment": {"python": sys.version, "platform": sys.platform,
        "database": "temporary SQLite", "server": "in-process FastAPI TestClient; HTTP routing overhead included",
        "llm": "disabled", "memory": "Windows process working set and process high-water mark; timers run without tracemalloc"},
        "order": profiles, "seeds": args.seeds, "results": results, "database_path": str(dbpath)}
    output = args.output or (root / "artifacts" / "wgs2-performance" / "matched.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)
    for row in results:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
