"""T1 ORM costs in a disposable SQLite database; never opens everreach.db."""
import json
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory
import time
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.game.world.seed import create_campaign
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.terrain.address import tile_at, level_for_spacing
from app.game.world.genesis.terrain.service import (initialize_terrain, materialize_terrain_tile,
    query_altitude, clear_terrain_cache)


def main():
    with TemporaryDirectory(prefix="everreach-t1-") as temp:
        engine = create_engine(f"sqlite:///{Path(temp).as_posix()}/terrain.db")
        event.listen(engine, "connect", enable_sqlite_foreign_keys)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            campaign = create_campaign(db, "T1 disposable benchmark", world_seed=42)
            initialize_world(db, campaign.id, FormationConfigV4(macro_level=2))
            initialize_terrain(db, campaign.id)
            db.commit()
            campaign_id = campaign.id
            tile = tile_at(SurfacePoint(3, 2, 1), level_for_spacing(63_710_000, 2))
            start = time.perf_counter()
            materialize_terrain_tile(db, campaign_id, tile)
            db.commit()
            creation = time.perf_counter()-start
        clear_terrain_cache()
        with Session(engine) as db:
            start = time.perf_counter()
            materialize_terrain_tile(db, campaign_id, tile)
            reload = time.perf_counter()-start
            samples = []
            for i in range(30):
                point = tile.point(i%17, (i*7)%17, 16)
                start = time.perf_counter()
                query_altitude(db, campaign_id, point)
                samples.append((time.perf_counter()-start)*1000)
        engine.dispose()
    result = {"seed": 42, "radius_m": 63_710_000, "sample_intervals": 16,
        "create_tile_and_commit_seconds": creation, "cold_reopen_tile_seconds": reload,
        "authoritative_orm_point_query_median_ms": statistics.median(samples),
        "scope": "disposable SQLite, one 289-sample tile, V4 creation/schema setup excluded; wall time, not RSS"}
    output = Path(__file__).resolve().parents[2]/"artifacts/terrain-t1/persistence-benchmark.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
