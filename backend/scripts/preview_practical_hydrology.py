"""Real P1 flow through the existing W2 ledger, in disposable SQLite only."""
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
from scripts.preview_water_reconciliation import import_snapshots
from app.game.world.genesis.terrain.field import checksum
from app.game.world.genesis.water_reconciliation.config import RevisionRequest, TransferIntent
from app.game.world.genesis.water_reconciliation.service import (initialize_reconciliation, prepare_water_domain,
    reconcile, get_water_domain, get_revision)
from app.game.world.genesis.water_reconciliation.practical.config import PracticalConfig
from app.game.world.genesis.water_reconciliation.practical.service import (initialize_practical_hydrology,
    prepare_natural_passage, get_local_account, POOL)
from app.game.world.genesis.water_reconciliation.practical.preview import write_preview
from app.game.world.genesis.water_reconciliation.practical.future import future_forcing_proposal


def main():
    root = Path(__file__).resolve().parents[2]
    output = root/"artifacts/practical-hydrology-p1"
    probe = json.loads((output/"probe.json").read_text())
    proof = probe["found"]
    if proof is None:
        raise RuntimeError("No natural proof found; do not fabricate a positive transfer")
    with TemporaryDirectory(prefix="everreach-p1-") as temporary:
        engine = create_engine(f"sqlite:///{Path(temporary).as_posix()}/p1.db")
        event.listen(engine, "connect", enable_sqlite_foreign_keys)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            cid, w1_row, water, _, _ = import_snapshots(db, 42, 63_710_000, 3982)
            source_hash = checksum(w1_row.plan)
            initialize_reconciliation(db, cid, cutover_minute=0)
            initialize_practical_hydrology(db, cid, PracticalConfig.model_validate(proof["config"]))
            started = time.perf_counter()
            evidence = prepare_natural_passage(db, cid, proof)
            preparation = time.perf_counter()-started
            data = evidence.baseline
            node = evidence.node
            prepare_water_domain(db, cid, node)
            original = get_water_domain(db, cid, node)
            quota = proof["allocation"]["vertex_quota_liters"]
            amount = quota[proof["source_vertex"]]+quota[proof["target_vertex"]]
            allocation = RevisionRequest(operation_id="L1:"+proof["proof_id"], logical_minute=0,
                expected_heads={str(node): original["head_id"]}, transfers=[TransferIntent(transfer_id="L1:"+proof["proof_id"],
                    source_node=node, target_node=node, source_account="w1:surface", target_account=POOL,
                    amount_liters=amount, evidence_keys=[evidence.evidence_key])])
            allocated = reconcile(db, cid, allocation)
            parent = get_water_domain(db, cid, node)
            before_local = {name: get_local_account(db, cid, data[name]) for name in ("source_account", "target_account")}
            request = RevisionRequest(operation_id="K1:"+proof["proof_id"], logical_minute=proof["config"]["episode_minutes"],
                expected_heads={str(node): parent["head_id"]}, transfers=[TransferIntent(transfer_id="K1:"+proof["proof_id"],
                    source_node=node, target_node=node, source_account=data["source_account"], target_account=data["target_account"],
                    amount_liters=proof["suggested_transfer_liters"], evidence_keys=[evidence.evidence_key])])
            tracemalloc.start()
            started = time.perf_counter()
            moved = reconcile(db, cid, request)
            elapsed = time.perf_counter()-started
            retained, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert moved.payload["local_reconciliation"]["delivered_liters"] > 0
            assert reconcile(db, cid, request).revision_id == moved.revision_id
            after_local = {name: get_local_account(db, cid, data[name]) for name in ("source_account", "target_account", "wetting_account")}
            final = get_water_domain(db, cid, node)
            assert sum(final["state"]["accounts"].values()) == sum(original["state"]["accounts"].values())
            assert checksum(w1_row.plan) == source_hash
            ids = cid, moved.revision_id
            records = {"allocation": allocated.payload, "flow": moved.payload, "proof": proof,
                "evidence": data, "before_local": before_local, "after_local": after_local}
            from app.game.world.genesis.terrain.address import TerrainTile
            records["future_forcing_proposal"] = future_forcing_proposal(water, TerrainTile(*proof["allocation"]["tile"]),
                PracticalConfig.model_validate(proof["config"]), cutover_minute=0, cycle=0, period=0)
            db.commit()
        with Session(engine) as reopened:
            assert get_revision(reopened, *ids)["payload"] == records["flow"]
            assert get_local_account(reopened, cid, data["target_account"])["liters"] == after_local["target_account"]["liters"]
        engine.dispose()
    summary = {"seed": 42, "radius_m": 63_710_000, "source_node": node,
        "source_was_in_fixed_W1_manifest": node in dict(water.manifest), "trials": probe["trials"],
        "localized_liters": amount, "source_before_liters": before_local["source_account"]["liters"],
        "source_after_liters": after_local["source_account"]["liters"],
        "receiver_before_liters": before_local["target_account"]["liters"],
        "receiver_after_liters": after_local["target_account"]["liters"],
        "retained_in_reach_liters": after_local["wetting_account"]["liters"],
        "delivered_liters": records["flow"]["local_reconciliation"]["delivered_liters"],
        "parent_residual_liters": records["flow"]["budgets"][str(node)]["residual_liters"],
        "child_residual_liters": records["flow"]["local_reconciliation"]["residual_liters"],
        "capacity": proof["capacity"], "historical_precipitation_mm": list(water.precipitation_mm[i][node] for i in range(4)),
        "historical_local_runoff_liters": list(p["fluxes"]["local_runoff"][node] for p in water.solution.periods),
        "W1_checksum_before_after": source_hash, "terrain_modified": False, "perennial": None,
        "benchmark": {"proof_preparation_seconds": preparation, "instrumented_flow_seconds": elapsed,
                      "tracemalloc_peak_bytes": peak, "retained_bytes": retained,
                      "scope": "existing source snapshot import/search excluded; instrumented SQLite P1/W2 revision"}}
    (output/"result.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    (output/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    from app.game.world.genesis.terrain.field import TerrainSampler, build_terrain_plan
    from scripts.preview_water import sources
    source, _, _ = sources(42, 63_710_000)
    write_preview(records, summary, TerrainSampler(build_terrain_plan(source)), output)
    print(json.dumps(summary, default=str))


if __name__ == "__main__":
    main()
