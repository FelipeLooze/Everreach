"""Disposable SQLite benchmark. Never opens or migrates everreach.db."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import statistics
import time
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.game.world.seed import create_campaign
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.service import initialize_hydrology
from app.game.world.genesis.hydrology.config import HydrologyConfig
from app.game.world.genesis.hydrology.regional_service import initialize_regional_hydrology
from app.game.world.genesis.terrain.service import initialize_terrain
from app.game.world.genesis.terrain.address import tile_at
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.hydro_geometry.config import GeometryRequest, Anchor
from app.game.world.genesis.hydro_geometry.service import initialize_geometry, materialize_geometry, get_geometry, clear_geometry_cache


def main():
    with TemporaryDirectory(prefix="everreach-g1-") as folder:
        engine = create_engine(f"sqlite:///{Path(folder).as_posix()}/geometry.db")
        event.listen(engine, "connect", enable_sqlite_foreign_keys)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            c = create_campaign(db, "G1 disposable benchmark", world_seed=42)
            cid = c.id
            initialize_world(db, cid, FormationConfigV4(macro_level=2))
            initialize_hydrology(db, cid, HydrologyConfig(level=2))
            initialize_regional_hydrology(db, cid)
            initialize_terrain(db, cid)
            initialize_geometry(db, cid)
            db.commit()
            tile = tile_at(SurfacePoint(3, 2, 1), 20)
            req = GeometryRequest(tile=list(vars(tile).values()), anchors=[
                Anchor(id="in", point=list(tile.point(0, 4, 8).xyz), role="ingress"),
                Anchor(id="out", point=list(tile.point(8, 4, 8).xyz), role="outlet")])
            start = time.perf_counter()
            row = materialize_geometry(db, cid, req)
            rid = row.request_id
            db.commit()
            prepare = time.perf_counter()-start
        clear_geometry_cache()
        with Session(engine) as db:
            start = time.perf_counter()
            get_geometry(db, cid, rid)
            reopen = time.perf_counter()-start
            durations = []
            for _ in range(20):
                start = time.perf_counter()
                get_geometry(db, cid, rid)
                durations.append((time.perf_counter()-start)*1000)
        engine.dispose()
    report = {"seed": 42, "radius_m": 63_710_000, "h1_level": 2, "g1_grid_intervals": 8,
        "create_and_commit_seconds": prepare, "cold_reopen_seconds": reopen,
        "current_evidence_query_median_ms": statistics.median(durations),
        "scope": "disposable SQLite; source creation/schema excluded; header/checksum/event checks included; no RSS measurement"}
    output = Path(__file__).resolve().parents[2]/"artifacts/hydro-geometry-g1/persistence-benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
