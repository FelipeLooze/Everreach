"""Opt-in J1 persistence, no public map, inventory or campaign-generation hooks."""
from copy import deepcopy
from app.db.models.world_geology import GenesisGeologyPlan, GenesisGeologicalUnit, GenesisMineralDeposit
from ..terrain.service import get_terrain_sampler
from ..terrain.field import checksum
from .field import build_geology_plan, load_geology_plan
from .adapter import adapt_unit, evaluate_opportunities
from .calibration import select_test_deposits, ExperimentalCalibration


def initialize_geology(db, campaign_id, config=None):
    existing = db.get(GenesisGeologyPlan, campaign_id)
    if existing is not None:
        plan = get_geology_plan(db, campaign_id)
        if config is not None and config.model_dump() != plan.data["config"]:
            raise ValueError("Cannot silently reconfigure geological authority")
        return existing
    terrain = get_terrain_sampler(db, campaign_id).plan
    plan = build_geology_plan(terrain, config)
    row = GenesisGeologyPlan(campaign_id=campaign_id, geology_version=1, signature=plan.signature,
                            baseline=plan.to_dict(), baseline_checksum=checksum(plan.to_dict()))
    db.add(row)
    db.flush()
    return row


def get_geology_plan(db, campaign_id):
    row = db.get(GenesisGeologyPlan, campaign_id)
    if row is None:
        raise ValueError("Initialize J1 explicitly; no auto-activation")
    if type(row.geology_version) is not int or row.geology_version != 1 or checksum(row.baseline) != row.baseline_checksum:
        raise ValueError("Saved J1 checksum/version mismatch")
    plan = load_geology_plan(row.baseline, get_terrain_sampler(db, campaign_id).plan)
    if row.signature != plan.signature:
        raise ValueError("Saved J1 signature mismatch")
    return plan


def materialize_geological_unit(db, campaign_id, point):
    plan = get_geology_plan(db, campaign_id)
    unit = plan.unit_at(point)
    row = db.get(GenesisGeologicalUnit, (campaign_id, unit["geological_unit_id"]))
    if row is not None:
        if checksum(row.baseline) != row.baseline_checksum or row.baseline != unit:
            raise ValueError("Established geological unit mismatch; refusing regeneration")
        return row
    baseline = deepcopy(unit)
    row = GenesisGeologicalUnit(campaign_id=campaign_id, unit_id=unit["geological_unit_id"], baseline=baseline,
                               baseline_checksum=checksum(baseline), changes={})
    db.add(row)
    db.flush()
    return row


def query_geology(db, campaign_id, point, *, baseline_only=False):
    if type(baseline_only) is not bool:
        raise ValueError("Explicit geological event policy required")
    plan = get_geology_plan(db, campaign_id)
    unit = plan.unit_at(point)
    row = db.get(GenesisGeologicalUnit, (campaign_id, unit["geological_unit_id"]))
    if row is not None:
        if checksum(row.baseline) != row.baseline_checksum or row.baseline != unit:
            raise ValueError("Saved geological unit mismatch")
        if row.changes and not baseline_only:
            raise ValueError("Geological events require an explicit overlay; baseline_only is diagnostic")
        unit = row.baseline
    contract = adapt_unit(unit, plan.signature)
    return {"unit": deepcopy(unit), "contract": contract, "assessment": evaluate_opportunities(contract),
            "baseline_only": baseline_only, "deposits_generated_by_query": False}


def materialize_test_deposit(db, campaign_id, deposit_id, *, experimental=False, calibration=None):
    if experimental is not True:
        raise ValueError("J1 deposit generation disabled outside explicit disposable experiments")
    # A JR1 campaign has one source authority. Do not combine the old macro
    # experiment with regional reserves. Inspection preserves pre-JR1 schemas.
    from sqlalchemy import inspect
    if inspect(db.connection()).has_table("genesis_regional_geology"):
        from app.db.models.world_geology_regional import GenesisRegionalGeology
        if db.get(GenesisRegionalGeology,campaign_id) is not None:
            raise ValueError("JR1 is active; macro experimental deposits require an explicit allocation migration")
    plan = get_geology_plan(db, campaign_id)
    calibration = calibration or ExperimentalCalibration()
    # Only the proposed calibration may be persisted; sensitivity runs are read-only.
    if calibration != ExperimentalCalibration():
        raise ValueError("Sensitivity calibration is not approved for persistent test deposits")
    proposal = next((d for d in select_test_deposits(plan, calibration) if d["deposit_id"] == deposit_id), None)
    if proposal is None:
        raise ValueError("Deposit not selected by the bounded deterministic test budget")
    proposal = {**proposal,"eligible_not_instantiated":False,"state":"experimental_instantiated"}
    existing = db.get(GenesisMineralDeposit, (campaign_id, deposit_id), populate_existing=True)
    if existing is not None:
        if checksum(existing.baseline) != existing.baseline_checksum or existing.baseline != proposal or not 0 <= existing.remaining_units <= proposal["initial_volume_units"]:
            raise ValueError("Finite deposit mismatch; no regeneration")
        return existing
    unit = next(u for u in plan.units if u["geological_unit_id"] == proposal["geological_unit_id"])
    from ..sphere_topology import SurfacePoint
    saved = materialize_geological_unit(db, campaign_id, SurfacePoint(*unit["center"]))
    if saved.changes:
        raise ValueError("Changed geology requires reconciliation before new deposit creation")
    row = GenesisMineralDeposit(campaign_id=campaign_id, deposit_id=deposit_id, unit_id=saved.unit_id,
        baseline=proposal, baseline_checksum=checksum(proposal), remaining_units=proposal["initial_volume_units"])
    db.add(row)
    db.flush()
    return row
