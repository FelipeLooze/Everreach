"""Offline J1/D14 experiments, never opens or migrates the real save database."""
import json
from pathlib import Path
from collections import Counter
import time
import tracemalloc
from app.game.world.genesis.formation_plan import build_plan, load_plan
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.terrain.field import build_terrain_plan, checksum
from app.game.world.genesis.geology.field import build_geology_plan
from app.game.world.genesis.geology.catalog import load_catalog
from app.game.world.genesis.geology.adapter import adapt_unit, evaluate_opportunities
from app.game.world.genesis.geology.calibration import select_test_deposits, ExperimentalCalibration, RATES, WORLD_CAPS
from app.game.world.genesis.geology.preview import write_preview
from app.game.world.genesis.sphere_topology import CellKey, cell_center
from app.game.world.genesis.sphere_area import cell_solid_angle

ROOT = Path(__file__).resolve().parents[2]
SEEDS = [42,0,1,2,3,7,11,17,29,73,101,2026,4096,12345,98765]


def source_plan(seed, radius):
    path = ROOT/f"artifacts/hydrology-h1/seed-{seed}-r{radius}/source-plan.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        return load_plan(saved, seed, FormationConfigV4.model_validate(saved["config"]))
    return build_plan(seed, FormationConfigV4(radius_m=radius))


def experiment(seed, radius, output, *, plot=False):
    source = source_plan(seed, radius)
    terrain = build_terrain_plan(source)
    original = checksum(source.to_dict())
    started = time.perf_counter()
    plan = build_geology_plan(terrain)
    prepared = time.perf_counter()-started
    catalog = load_catalog()
    units = plan.units
    assessments = [evaluate_opportunities(adapt_unit(u, plan.signature), catalog) for u in units]
    opportunities = [o for a in assessments for o in a["opportunities"]]
    # Area-weighted geographic diagnostic, not counts treated as area fractions.
    areas = Counter()
    for face in range(6):
        for y in range(16):
            for x in range(16):
                key = CellKey(face,4,x,y)
                unit = plan.unit_at(cell_center(key))
                areas[unit["substrates"][0]] += cell_solid_angle(key)
    selected = select_test_deposits(plan)
    summary = {"seed": seed, "radius_m": radius, "signature": plan.signature, "units": len(units),
        "units_by_substrate": dict(sorted(Counter(s for u in units for s in u["substrates"]).items())),
        "sampled_area_fraction_by_substrate": {s:a/sum(areas.values()) for s,a in sorted(areas.items())},
        "units_eligible_by_bridge": {m:sum(a["bridges"][m]["eligible"] for a in assessments) for m in catalog["bridges"]},
        "blocked_evidence_by_bridge": {m:dict(Counter(reason for a in assessments for reason in a["bridges"][m]["missing"])) for m in catalog["bridges"]},
        "unique_unit_material_opportunities": len(opportunities),
        "opportunities_by_material": dict(sorted(Counter(o["material_id"] for o in opportunities).items())),
        "eligible_alternative_routes": dict(sorted(Counter(r["route_id"] for o in opportunities for r in o["routes"] if r["route_id"].startswith("EV-GEO-ALT")).items())),
        "units_with_any_opportunity": len({o["geological_unit_id"] for o in opportunities}),
        "proposed_test_deposits": len(selected), "selected_by_rarity": dict(Counter(d["rarity"] for d in selected)),
        "sensitivity_deposit_counts": {str(f):len(select_test_deposits(plan,ExperimentalCalibration(rate_factor_ppm=f))) for f in (0,500000,1000000,2000000)},
        "prepare_seconds": prepared, "serialized_bytes": len(json.dumps(plan.to_dict()).encode()),
        "V4_unchanged": checksum(source.to_dict()) == original, "real_save_modified": False}
    folder = output/f"seed-{seed}-r{radius}"
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"plan.json").write_text(json.dumps(plan.to_dict(),indent=2),encoding="utf-8")
    (folder/"metrics.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    (folder/"selected-test-deposits.json").write_text(json.dumps(selected,indent=2),encoding="utf-8")
    if plot:
        write_preview(plan,folder/"geology.png",seed=seed)
    return summary, plan


def persistence_demo(plan, output):
    """Real source + J1 + opportunity + finite deposit committed and reopened."""
    import tempfile
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session
    from app.db.base import Base
    from app.db.database import enable_sqlite_foreign_keys
    from app.game.world.seed import create_campaign
    from app.game.world.genesis.service import initialize_world
    from app.game.world.genesis.terrain.service import initialize_terrain
    from app.game.world.genesis.geology.service import initialize_geology, get_geology_plan, materialize_test_deposit
    selected = select_test_deposits(plan)
    if not selected:
        return None
    with tempfile.TemporaryDirectory(prefix="everreach-j1-") as directory:
        engine = create_engine(f"sqlite:///{Path(directory,'proof.db').as_posix()}")
        event.listen(engine,"connect",enable_sqlite_foreign_keys)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            seed = int(output.name.split("seed-")[-1].split("-r")[0])
            campaign = create_campaign(db,"J1 disposable proof",world_seed=seed)
            initialize_world(db,campaign.id,FormationConfigV4(radius_m=plan.data["radius_m"]))
            initialize_terrain(db,campaign.id)
            initialize_geology(db,campaign.id)
            actual = get_geology_plan(db,campaign.id)
            if actual.signature != plan.signature:
                raise ValueError("Persisted J1 proof must match the measured real source")
            proposal = selected[0]
            row = materialize_test_deposit(db,campaign.id,proposal["deposit_id"],experimental=True)
            cid, identifier, initial = campaign.id,row.deposit_id,row.remaining_units
            # No extraction API is introduced: just persist the finite initial stock.
            db.commit()
        with Session(engine) as db:
            saved = materialize_test_deposit(db,cid,identifier,experimental=True)
            assert saved.remaining_units == initial and saved.baseline["deposit_id"] == proposal["deposit_id"]
            assert saved.baseline["state"] == "experimental_instantiated"
            unit = next(u for u in plan.units if u["geological_unit_id"] == proposal["geological_unit_id"])
            result = {"deposit": saved.baseline, "remaining_units_after_reopen": saved.remaining_units,
                "unit": unit, "contract": adapt_unit(unit,plan.signature), "committed_and_reopened": True,
                "database": "temporary_disposable_SQLite", "real_save_modified": False}
        engine.dispose()
    (output/"persistent-proof.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


def main():
    output = ROOT/"artifacts/geology-j1"
    output.mkdir(parents=True,exist_ok=True)
    cases = [(s,63710000) for s in SEEDS]+[(42,r) for r in (6371000,637100000,1000000000000)]
    summaries = []
    demonstration = None
    for seed,radius in cases:
        summary,plan = experiment(seed,radius,output,plot=seed in (42,0,2026) and radius==63710000)
        summaries.append(summary)
        print(json.dumps({k:summary[k] for k in ("seed","radius_m","units","unique_unit_material_opportunities","proposed_test_deposits")}))
        if demonstration is None and summary["proposed_test_deposits"]:
            demonstration = persistence_demo(plan,output/f"seed-{seed}-r{radius}")
    source = source_plan(42,63710000)
    terrain = build_terrain_plan(source)
    tracemalloc.start()
    started = time.perf_counter()
    measured = build_geology_plan(terrain)
    instrumented = time.perf_counter()-started
    retained,peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    suite = {"cases":summaries,"experimental_rates_per_million":RATES,"world_caps_per_material":WORLD_CAPS,
        "regional_cap_per_material":1,"legendary_random_deposits":0,"historical_v4_intensities_applied":False,
        "benchmark":{"instrumented_prepare_seconds":instrumented,"peak_bytes":peak,"retained_bytes":retained,
                     "scope":"J1 preparation; V4/T1 source already loaded; not RSS"},
        "persistent_demonstration": demonstration["deposit"]["deposit_id"] if demonstration else None,
        "runtime_autogeneration_enabled":False}
    (output/"suite.json").write_text(json.dumps(suite,indent=2),encoding="utf-8")


if __name__ == "__main__":
    main()
