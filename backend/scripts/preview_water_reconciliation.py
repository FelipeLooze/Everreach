"""W2 real-domain demo using exact prior snapshots in disposable SQLite only."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import tracemalloc
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.database import enable_sqlite_foreign_keys
from app.db.models.world_genesis import GenesisWorld
from app.db.models.world_hydrology import GenesisHydrologyPlan
from app.db.models.world_hydrology_regional import GenesisHydrologyRefinement, GenesisHydrologyRegion
from app.db.models.world_climate import GenesisClimatePlan
from app.db.models.world_water import GenesisWaterPlan
from app.db.models.world_hydro_geometry import GenesisHydroGeometryEvidence
from app.game.world.seed import create_campaign
from app.game.world.genesis.formation_plan import load_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.hydrology.plan import load_hydrology_plan
from app.game.world.genesis.hydrology.regional import RegionalHydrologyConfig, regional_signature
from app.game.world.genesis.climate.plan import load_climate_plan
from app.game.world.genesis.water.plan import load_water_plan
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.terrain.service import initialize_terrain
from app.game.world.genesis.hydro_geometry.service import initialize_geometry
from app.game.world.genesis.hydro_geometry.geometry import validate_geometry
from app.game.world.genesis.hydro_geometry.config import GeometryRequest
from app.game.world.genesis.hydro_geometry.service import get_geometry_plan
from app.game.world.genesis.water_reconciliation.service import (initialize_reconciliation, prepare_water_domain,
    register_geometry_evidence, register_coast_evidence, reconcile, get_water_domain, get_revision)
from app.game.world.genesis.water_reconciliation.coast import CoastRequest
from app.game.world.genesis.water_reconciliation.config import RevisionRequest, TransferIntent
from app.game.world.genesis.water_reconciliation.preview import write_preview

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def import_snapshots(db, seed, radius, node):
    # Existing authority is loaded/validated, never re-solved to make a demo pass.
    hp = ROOT/f"artifacts/hydrology-h1/seed-{seed}-r{radius}"
    wp = ROOT/f"artifacts/water-w1/seed-{seed}-r{radius}"
    gp = ROOT/f"artifacts/hydro-geometry-g1/seed-{seed}-r{radius}-node-{node}"
    source_data = read(hp/"source-plan.json")
    source = load_plan(source_data, seed, FormationConfigV4.model_validate(source_data["config"]))
    h1_data = read(hp/"plan.json")
    h1 = load_hydrology_plan(h1_data, source.signature, radius, source.config.sea_level_m)
    climate_data = read(ROOT/f"artifacts/climate-calibration-0.5.1/seed-{seed}-r{radius}/c2-plan.json")
    climate = load_climate_plan(climate_data, source.signature, h1.signature, radius, source.config.sea_level_m)
    water_data = read(wp/"plan.json")
    hr_config = RegionalHydrologyConfig()
    hr_signature = regional_signature(h1, hr_config)
    water = load_water_plan(water_data, h1, climate, hr_signature)
    c = create_campaign(db, f"W2 offline {seed}/{radius}", world_seed=seed)
    cid = c.id
    db.add(GenesisWorld(campaign_id=cid, world_seed=seed, config=source.config.model_dump(), plan=source_data))
    db.flush()
    db.add(GenesisHydrologyPlan(campaign_id=cid, hydrology_version=1, source_signature=source.signature,
        source_checksum=checksum(source_data), signature=h1.signature, config=h1.config.model_dump(),
        payload_checksum=checksum(h1_data), plan=h1_data))
    db.flush()
    db.add(GenesisHydrologyRefinement(campaign_id=cid, refinement_version=1, hydrology_signature=h1.signature,
        hydrology_checksum=checksum(h1_data), signature=hr_signature, config=hr_config.model_dump()))
    db.add(GenesisClimatePlan(campaign_id=cid, climate_version=2, source_signature=source.signature,
        source_checksum=checksum(source_data), hydrology_signature=h1.signature, hydrology_checksum=checksum(h1_data),
        signature=climate.signature, config=climate.config.model_dump(), payload_checksum=checksum(climate_data), plan=climate_data))
    db.flush()
    row = GenesisWaterPlan(campaign_id=cid, water_version=1, signature=water.signature, config=water.config.model_dump(),
        hydrology_signature=h1.signature, hydrology_checksum=checksum(h1_data), climate_signature=climate.signature,
        climate_checksum=checksum(climate_data), hr_signature=hr_signature, manifest=list(water.manifest),
        payload_checksum=checksum(water_data), plan=water_data)
    db.add(row)
    db.flush()
    for region in read(wp/"hr1-evidence.json"):
        db.add(GenesisHydrologyRegion(campaign_id=cid, node=region["node"], signature=hr_signature,
            baseline_checksum=checksum(region), baseline=region, changes={}))
    db.flush()
    initialize_terrain(db, cid)
    initialize_geometry(db, cid)
    g1, _ = get_geometry_plan(db, cid)
    gids = []
    for name in ("legacy-ports", "t1-candidate-ports", "local-a", "local-b"):
        data = read(gp/name/"evidence.json")
        validate_geometry(g1, GeometryRequest.model_validate(data["request"]), data)
        db.add(GenesisHydroGeometryEvidence(campaign_id=cid, request_id=data["request_id"],
            baseline_checksum=checksum(data), baseline=data, changes={}))
        gids.append(data["request_id"])
    db.flush()
    return cid, row, water, gids, gp


def run(seed, radius, node, output):
    with TemporaryDirectory(prefix="everreach-w2-") as temporary:
        engine = create_engine(f"sqlite:///{Path(temporary).as_posix()}/demo.db")
        event.listen(engine, "connect", enable_sqlite_foreign_keys)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            cid, w1_row, water, gids, gfolder = import_snapshots(db, seed, radius, node)
            before = checksum(w1_row.plan)
            started = time.perf_counter()
            initialize_reconciliation(db, cid, cutover_minute=0)
            prepare_water_domain(db, cid, node)
            keys = [register_geometry_evidence(db, cid, gid, logical_minute=0).evidence_key for gid in gids]
            preparation = time.perf_counter()-started
            coast_report = None
            if seed == 42 and radius == 63_710_000:
                coast_data = read(ROOT/"artifacts/hydro-geometry-g1/coast-seed-42/evidence.json")
                g1, _ = get_geometry_plan(db, cid)
                validate_geometry(g1, GeometryRequest.model_validate(coast_data["request"]), coast_data)
                db.add(GenesisHydroGeometryEvidence(campaign_id=cid, request_id=coast_data["request_id"],
                    baseline_checksum=checksum(coast_data), baseline=coast_data, changes={}))
                db.flush()
                coast_key = register_geometry_evidence(db, cid, coast_data["request_id"], logical_minute=0).evidence_key
                point = next(a["point"] for a in coast_data["request"]["anchors"] if a["role"] == "outlet")
                from app.game.world.genesis.sphere_topology import SurfacePoint
                reference = g1.terrain.source.component_at(SurfacePoint(*point)).id
                # An intentionally incomplete real coastal attempt: T1 is land here,
                # so this must NOT become an ocean export or a designated reference.
                coast_report = register_coast_evidence(db, cid, CoastRequest(g1_keys=[coast_key],
                    route_ids=[coast_data["routes"][0]["id"]], reference_point=point,
                    reference_component_id=reference), logical_minute=0).baseline
                assert coast_report["status"] == "pending" and not coast_report["export_authorized"]
            revisions, timings = [], []
            memory = {}
            for season in range(4):
                current = get_water_domain(db, cid, node)
                accounts = current["state"]["accounts"]
                account = next((name for name in ("w1:unresolved", "w1:channel", "w1:depression", "w1:surface", "w1:soil", "w1:snow") if accounts[name]), "w1:unresolved")
                amount = min(1_000_000, accounts[account])
                move = TransferIntent(transfer_id=f"request-{node}-{season}", source_node=node, target_node=node,
                    source_account=account, amount_liters=amount, evidence_keys=keys if node == 3982 else keys[-2:])
                req = RevisionRequest(operation_id=f"season-{season}", logical_minute=water.year_days*1440*season//4,
                    expected_heads={str(node): current["head_id"]}, evidence_keys=keys, transfers=[move])
                if seed == 42 and radius == 63_710_000 and season == 0:
                    tracemalloc.start()
                start = time.perf_counter()
                revision = reconcile(db, cid, req)
                timings.append(time.perf_counter()-start)
                if tracemalloc.is_tracing():
                    retained, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    memory = {"retained_bytes": retained, "peak_bytes": peak}
                revisions.append(revision.payload)
            assert checksum(w1_row.plan) == before
            domain = get_water_domain(db, cid, node)
            rid = domain["head_id"]
            db.commit()
        with Session(engine) as reopened:
            assert get_water_domain(reopened, cid, node)["state_checksum"] == domain["state_checksum"]
            assert get_revision(reopened, cid, rid)["payload"] == revisions[-1]
        engine.dispose()
    folder = output/f"seed-{seed}-r{radius}-node-{node}"
    report = write_preview(water, node, revisions, folder, seed=seed, radius_m=radius,
        g1_image=gfolder/"legacy-ports/geometry.png")
    report.update(seed=seed, radius_m=radius, node=node, W1_checksum_before_after=before,
        prepared_W2_domains=1, registered_G1_evidence=4, benchmark={"preparation_seconds": preparation,
        "revision_seconds": timings, "memory": memory, "first_revision_instrumented": bool(memory),
        "scope": "W2 SQLite execution; source snapshot import excluded; memory is tracemalloc, not RSS"})
    (folder/"revisions.json").write_text(json.dumps(revisions, indent=2), encoding="utf-8")
    (folder/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if coast_report is not None:
        (folder/"coast-evidence.json").write_text(json.dumps(coast_report, indent=2), encoding="utf-8")
    print(json.dumps({"seed": seed, "radius_m": radius, "node": node, "residual": report["max_absolute_residual_liters"],
        "applied_liters": report["applied_transfer_liters"], "revision_seconds": timings}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT/"artifacts/water-reconciliation-w2")
    args = parser.parse_args()
    cases = [(42, 63710000, 3982), (0, 63710000, 874), (2026, 63710000, 141),
        (42, 6371000, 136), (42, 637100000, 37), (42, 10**12, 37)] if args.suite else [(42, 63710000, 3982)]
    reports = [run(seed, radius, node, args.output) for seed, radius, node in cases]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"suite.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
