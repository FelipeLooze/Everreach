"""W2 opt-in local revisions. No commits, global re-solve, or movement hooks."""
from copy import deepcopy
from sqlalchemy import update
from app.db.models.campaign import WorldTime
from app.db.models.world_hydro_geometry import GenesisHydroGeometryEvidence
from app.db.models.world_water_reconciliation import (GenesisWaterReconciliation, GenesisWaterDomain,
    GenesisWaterRevision, GenesisWaterReconciliationEvidence, GenesisWaterTransfer)
from ..terrain.field import checksum
from ..hydro_geometry.service import get_geometry_plan, get_geometry
from .config import ReconciliationConfig
from .sources import water_baseline
from .ledger import opening_state, genesis_head, validate_state, apply_batch
from .admission import assess_geometry, assess_transfer, domain_of
from .events import event_snapshot
from .coast import CoastRequest, connection_evidence


def _climate_sources(water):
    if water.config.source_climate_version==2:
        return {'c2_signature':water.climate_signature}
    return {'climate_signature':water.climate_signature,'climate_version':3,
        'climate_forcing_contract':water.config.forcing_contract}


def _context(db, campaign_id):
    baseline_row, water = water_baseline(db, campaign_id)
    g1, _ = get_geometry_plan(db, campaign_id)
    row = db.get(GenesisWaterReconciliation, campaign_id)
    if row is None:
        raise ValueError("Initialize W2 explicitly; no save conversion is automatic")
    config = ReconciliationConfig.model_validate(row.config)
    sources = {"w1_signature": water.signature, "w1_checksum": baseline_row.payload_checksum,
        "g1_signature": g1.signature, "g1_checksum": checksum(g1.to_dict()),
        "t1_signature": g1.terrain.signature, "h1_signature": water.hydrology.signature,
        "hr1_signature": water.hr_signature, **_climate_sources(water),
        "opening_policy": "W1_final_period_stocks_once_without_recrediting_fluxes"}
    expected = checksum(["water-reconciliation-w2", sources, config.model_dump(), row.cutover_minute])[:24]
    if type(row.water_version) is not int or row.water_version != 2 or row.signature != expected or row.sources != sources:
        raise ValueError("W2 pinned sources/version changed; explicit revision required")
    return row, config, water, g1


def initialize_reconciliation(db, campaign_id, config=None, *, cutover_minute=None):
    existing = db.get(GenesisWaterReconciliation, campaign_id)
    if existing is not None:
        row, pinned, _, _ = _context(db, campaign_id)
        if config is not None and config != pinned or cutover_minute is not None and cutover_minute != row.cutover_minute:
            raise ValueError("Cannot silently reconfigure W2")
        return row
    baseline_row, water = water_baseline(db, campaign_id)
    g1, _ = get_geometry_plan(db, campaign_id)
    config = config or ReconciliationConfig()
    allowed = {c.id for c in g1.terrain.source.components if c.kind == "water_body"}
    if any(c not in allowed for c in config.ocean_reference_component_ids):
        raise ValueError("W2 ocean references must name existing historical water components explicitly")
    if cutover_minute is None:
        clock = db.query(WorldTime).filter_by(campaign_id=campaign_id).one()
        cutover_minute = clock.total_minutes()
    if type(cutover_minute) is not int or not 0 <= cutover_minute <= 2**62:
        raise ValueError("Invalid explicit W2 cutover minute")
    sources = {"w1_signature": water.signature, "w1_checksum": baseline_row.payload_checksum,
        "g1_signature": g1.signature, "g1_checksum": checksum(g1.to_dict()),
        "t1_signature": g1.terrain.signature, "h1_signature": water.hydrology.signature,
        "hr1_signature": water.hr_signature, **_climate_sources(water),
        "opening_policy": "W1_final_period_stocks_once_without_recrediting_fluxes"}
    row = GenesisWaterReconciliation(campaign_id=campaign_id, water_version=2, config=config.model_dump(), sources=sources,
        cutover_minute=cutover_minute, write_epoch=0,
        signature=checksum(["water-reconciliation-w2", sources, config.model_dump(), cutover_minute])[:24])
    db.add(row)
    db.flush()
    return row


def prepare_water_domain(db, campaign_id, node):
    header, _, water, _ = _context(db, campaign_id)
    opening = opening_state(water, node)
    row = db.get(GenesisWaterDomain, (campaign_id, node))
    if row is not None:
        _validate_domain(row, header, opening)
        return row
    row = GenesisWaterDomain(campaign_id=campaign_id, node=node, head_id=genesis_head(header.signature, node, opening),
        state_version=0, last_minute=header.cutover_minute, opening_checksum=checksum(opening),
        state_checksum=checksum(opening), state=opening)
    db.add(row)
    db.flush()
    return row


def _validate_domain(row, header, opening):
    validate_state(row.state)
    if row.opening_checksum != checksum(opening) or row.state_checksum != checksum(row.state):
        raise ValueError("W2 domain checksum/origin mismatch")
    if row.state_version == 0 and row.head_id != genesis_head(header.signature, row.node, opening):
        raise ValueError("W2 opening head mismatch")


def _geometry_current(db, campaign_id, rid, config):
    tracked = db.get(GenesisHydroGeometryEvidence, (campaign_id, rid))
    if tracked is not None and tracked not in db.dirty and tracked not in db.new:
        db.refresh(tracked)
    historical = get_geometry(db, campaign_id, rid, baseline_only=True)
    geometry = historical["baseline"]
    events = event_snapshot(db, campaign_id, geometry, config.max_event_rows)
    status, error = "current", None
    try:
        get_geometry(db, campaign_id, rid)
    except ValueError as exc:
        status, error = "invalidated", str(exc)
    if not events["current"]:
        status = "invalidated"
    return geometry, historical["baseline_checksum"], events, status, error


def register_geometry_evidence(db, campaign_id, rid, *, logical_minute):
    header, config, water, _ = _context(db, campaign_id)
    if type(logical_minute) is not int or logical_minute < header.cutover_minute:
        raise ValueError("W2 evidence cannot be registered before cutover")
    geometry, digest, events, status, error = _geometry_current(db, campaign_id, rid, config)
    key = "g1:"+checksum([header.signature, rid, digest])[:32]
    row = db.get(GenesisWaterReconciliationEvidence, (campaign_id, key))
    if row is not None:
        if checksum(row.baseline) != row.checksum:
            raise ValueError("W2 evidence registry checksum mismatch")
        return row
    data = {"kind": "w2_g1_reference", "evidence_key": key, "g1_request_id": rid, "g1_checksum": digest,
        "registered_minute": logical_minute, "events": events, "observed_status": status, "error": error,
        "assessment": assess_geometry(geometry, config.required_probe_spacing_m), "sources": header.sources,
        "water_ledger_modified": False}
    row = GenesisWaterReconciliationEvidence(campaign_id=campaign_id, evidence_key=key, kind="g1",
        node=domain_of(geometry, water.hydrology.config.level), baseline=data, checksum=checksum(data))
    db.add(row)
    db.flush()
    return row


def _read_evidence(db, campaign_id, keys, config):
    geometries, statuses, provenance = {}, {}, {}
    if len(set(keys)) > config.max_evidence_per_revision:
        raise ValueError("W2 evidence budget exceeded")
    for key in sorted(set(keys)):
        row = db.get(GenesisWaterReconciliationEvidence, (campaign_id, key))
        if row is None:
            statuses[key] = "missing"
            provenance[key] = {"status": "missing_evidence_not_physical_blockage"}
            continue
        if checksum(row.baseline) != row.checksum:
            raise ValueError("W2 registered evidence checksum mismatch")
        if row.kind == "p1":
            from .practical.service import read_current
            geometry, events, status = read_current(db, campaign_id, row)
            geometries[key], statuses[key] = geometry, status
            provenance[key] = {"g1_request_id": geometry["request_id"], "checksum": row.checksum,
                "events": events, "status": status, "policy_extension": "P1"}
            continue
        if row.kind != "g1":
            continue
        geometry, digest, events, status, error = _geometry_current(db, campaign_id, row.baseline["g1_request_id"], config)
        if digest != row.baseline["g1_checksum"]:
            raise ValueError("G1 baseline was replaced after W2 registration")
        geometries[key], statuses[key] = geometry, status
        provenance[key] = {"g1_request_id": geometry["request_id"], "checksum": digest,
            "events": events, "status": status, "error": error}
    return geometries, statuses, provenance


def register_coast_evidence(db, campaign_id, request: CoastRequest, *, logical_minute):
    header, config, water, g1 = _context(db, campaign_id)
    if type(logical_minute) is not int or logical_minute < header.cutover_minute:
        raise ValueError("O1 evidence cannot predate W2 cutover")
    geometries, statuses, provenance = _read_evidence(db, campaign_id, request.g1_keys, config)
    data = connection_evidence(request, geometries, statuses, g1.terrain.source, water, config.required_probe_spacing_m,
                               config.ocean_reference_component_ids)
    key = "o1:"+checksum([header.signature, request.model_dump()])[:32]
    existing = db.get(GenesisWaterReconciliationEvidence, (campaign_id, key))
    if existing is not None:
        if checksum(existing.baseline) != existing.checksum:
            raise ValueError("O1 checksum mismatch")
        return existing
    data.update(evidence_key=key, registered_minute=logical_minute, provenance=provenance, sources=header.sources)
    from ..sphere_topology import SurfacePoint, cell_at
    from ..formation_plan import cell_index
    node = cell_index(cell_at(SurfacePoint(*request.reference_point), water.hydrology.config.level))
    row = GenesisWaterReconciliationEvidence(campaign_id=campaign_id, evidence_key=key, kind="o1", node=node,
        baseline=data, checksum=checksum(data))
    db.add(row)
    db.flush()
    return row


def _coast_current(db, campaign_id, key, config, water, g1, prepared=None):
    if key is None:
        return None
    row = db.get(GenesisWaterReconciliationEvidence, (campaign_id, key))
    if row is None:
        return None
    if row.kind != "o1" or checksum(row.baseline) != row.checksum:
        raise ValueError("Invalid W2 coastal evidence")
    request = CoastRequest.model_validate(row.baseline["request"])
    geometries, statuses, provenance = prepared or _read_evidence(db, campaign_id, request.g1_keys, config)
    data = connection_evidence(request, geometries, statuses, g1.terrain.source, water, config.required_probe_spacing_m,
                               config.ocean_reference_component_ids)
    return {**data, "provenance": provenance, "registered_checksum": row.checksum}


def reconcile(db, campaign_id, request):
    header, config, water, g1 = _context(db, campaign_id)
    canonical = request.canonical()
    request_hash = checksum(canonical)
    nodes = sorted(map(int, request.expected_heads))
    if any(t.source_node not in nodes or t.target_node is not None and t.target_node not in nodes for t in request.transfers):
        raise ValueError("W2 transfer endpoints must be explicitly locked domains")
    physical_keys = {k for t in request.transfers for k in t.evidence_keys}
    if physical_keys and db.query(GenesisWaterReconciliationEvidence.evidence_key).filter(
            GenesisWaterReconciliationEvidence.campaign_id == campaign_id,
            GenesisWaterReconciliationEvidence.evidence_key.in_(physical_keys), GenesisWaterReconciliationEvidence.kind == "p1").first():
        from .practical.service import reconcile_practical
        return reconcile_practical(db, campaign_id, request)
    keys = set(request.evidence_keys) | {k for t in request.transfers for k in t.evidence_keys}
    coast_keys = {t.coast_evidence_key for t in request.transfers if t.coast_evidence_key is not None}
    for key in sorted(coast_keys):
        coastal = db.get(GenesisWaterReconciliationEvidence, (campaign_id, key))
        if coastal is not None:
            if coastal.kind != "o1" or checksum(coastal.baseline) != coastal.checksum:
                raise ValueError("Invalid coastal evidence referenced by W2 revision")
            keys.update(coastal.baseline["request"]["g1_keys"])
    if (len(nodes) > config.max_domains_per_revision or len(keys)+len(coast_keys) > config.max_evidence_per_revision or
            len(request.transfers) > config.max_transfers_per_revision):
        raise ValueError("W2 local revision budget exceeded")
    if request.logical_minute < header.cutover_minute:
        raise ValueError("W2 cannot rewrite pre-cutover history")
    if db.get_bind().dialect.name != "sqlite":
        raise ValueError("W2 requires the tested SQLite writer fence; other engines need explicit event-serialization support")
    # Write BEFORE SAVEPOINT: pysqlite otherwise may release a top-level savepoint
    # as a commit, defeating caller rollback in a reopened read-only transaction.
    fence = db.execute(update(GenesisWaterReconciliation).where(GenesisWaterReconciliation.campaign_id == campaign_id,
        GenesisWaterReconciliation.signature == header.signature).values(write_epoch=GenesisWaterReconciliation.write_epoch+1),
        execution_options={"synchronize_session": False})
    if fence.rowcount != 1:
        raise ValueError("W2 writer fence source changed")
    db.flush()
    with db.begin_nested():
        existing = db.query(GenesisWaterRevision).filter_by(campaign_id=campaign_id, operation_id=request.operation_id).first()
        if existing is not None:
            if existing.request_checksum != request_hash:
                raise ValueError("W2 operation ID reused with a different intent")
            _validate_revision(existing)
            return existing
        rows, states = {}, {}
        for node in nodes:
            row = db.get(GenesisWaterDomain, (campaign_id, node), populate_existing=True)
            if row is None:
                raise ValueError("Prepare W2 domains explicitly before reconciling")
            _validate_domain(row, header, opening_state(water, node))
            if row.head_id != request.expected_heads[str(node)]:
                raise ValueError("Stale W2 predecessor; reload instead of overwriting history")
            if request.logical_minute < row.last_minute:
                raise ValueError("W2 logical time cannot move backwards")
            rows[node], states[node] = row, row.state
        transfer_ids = [t.transfer_id for t in request.transfers]
        if transfer_ids and db.query(GenesisWaterTransfer.transfer_id).filter(
                GenesisWaterTransfer.campaign_id == campaign_id, GenesisWaterTransfer.transfer_id.in_(transfer_ids)).first():
            raise ValueError("A W2 transfer was already applied; cannot debit it twice")
        geometries, statuses, provenance = _read_evidence(db, campaign_id, keys, config)
        coastal = {k: _coast_current(db, campaign_id, k, config, water, g1, (geometries, statuses, provenance)) for k in sorted(coast_keys)}
        admissions = {t.transfer_id: assess_transfer(t, geometries, statuses, water, config,
            coastal.get(t.coast_evidence_key)) for t in request.transfers}
        period = ((request.logical_minute-header.cutover_minute)*4//(water.year_days*1440))%4
        after, transfers, budgets = apply_batch(states, request.transfers, admissions, period)
        payload = {"kind": "water_revision_w2", "water_version": 2, "signature": header.signature,
            "request": canonical, "previous_heads": request.expected_heads, "logical_minute": request.logical_minute,
            "period": period, "sources": header.sources, "evidence": provenance,
            "coastal_evidence": coastal,
            "before": {str(k): v for k, v in states.items()}, "after": {str(k): v for k, v in after.items()},
            "budgets": {str(k): v for k, v in budgets.items()}, "transfers": transfers,
            "evidence_assessments": {key: assess_geometry(data, config.required_probe_spacing_m) for key, data in sorted(geometries.items())},
            "baseline_W1_mutated": False, "perennial": None}
        rid = checksum(["w2-revision", payload])[:32]
        import json
        if len(json.dumps(payload, separators=(",", ":")).encode()) > config.max_payload_bytes:
            raise ValueError("W2 revision persistence budget exceeded")
        revision = GenesisWaterRevision(campaign_id=campaign_id, revision_id=rid, operation_id=request.operation_id,
            request_checksum=request_hash, payload_checksum=checksum(payload), logical_minute=request.logical_minute,
            period=period, payload=payload)
        db.add(revision)
        db.flush()
        for node, row in rows.items():
            changed = db.execute(update(GenesisWaterDomain).where(GenesisWaterDomain.campaign_id == campaign_id,
                GenesisWaterDomain.node == node, GenesisWaterDomain.head_id == request.expected_heads[str(node)],
                GenesisWaterDomain.state_version == row.state_version).values(state=after[node], state_checksum=checksum(after[node]),
                    head_id=rid, state_version=row.state_version+1, last_minute=request.logical_minute),
                    execution_options={"synchronize_session": False})
            if changed.rowcount != 1:
                raise ValueError("Concurrent W2 domain change; entire revision rolled back")
            db.expire(row)
        for transfer in transfers:
            if transfer["status"] == "applied":
                db.add(GenesisWaterTransfer(campaign_id=campaign_id, transfer_id=transfer["transfer_id"], revision_id=rid, payload=transfer))
        db.flush()
        _validate_revision(revision)
        return revision


def _validate_revision(row):
    data = row.payload
    if (checksum(data) != row.payload_checksum or checksum(["w2-revision", data])[:32] != row.revision_id or
            data.get("kind") != "water_revision_w2" or data.get("water_version") != 2 or data.get("baseline_W1_mutated") is not False or
            data["request"]["operation_id"] != row.operation_id or row.period not in range(4) or
            checksum(data["request"]) != row.request_checksum or data["period"] != row.period or
            data["logical_minute"] != row.logical_minute):
        raise ValueError("W2 revision integrity failure")
    for node, budget in data["budgets"].items():
        before, after = data["before"][node], data["after"][node]
        validate_state(before)
        validate_state(after)
        if (sum(before["accounts"].values()) != budget["start_storage_liters"] or
                sum(after["accounts"].values()) != budget["end_storage_liters"] or
                budget["start_storage_liters"]+budget["inputs_liters"]-budget["outputs_liters"] != budget["end_storage_liters"] or
                budget["residual_liters"] != 0):
            raise ValueError("W2 stored ledger does not conserve water")
    expected_in = {k: 0 for k in data["budgets"]}
    expected_out = dict(expected_in)
    expected_export = dict(expected_in)
    for transfer in data["transfers"]:
        amount = transfer["applied_liters"]
        if type(amount) is not int or amount < 0 or amount > transfer["requested_liters"]:
            raise ValueError("Invalid W2 stored transfer quantity")
        if transfer["status"] == "applied":
            source = str(transfer["source_node"])
            expected_out[source] += amount
            if transfer["target_node"] is None:
                expected_export[source] += amount
            else:
                expected_in[str(transfer["target_node"])] += amount
        elif amount:
            raise ValueError("Pending W2 transfer cannot debit water")
    for node, budget in data["budgets"].items():
        if (budget["inputs_liters"] != expected_in[node] or budget["outputs_liters"] != expected_out[node] or
                budget["ocean_export_liters"] != expected_export[node]):
            raise ValueError("W2 confluence/transfer ledger mismatch")
    if "local_reconciliation" in data:
        from .practical.service import validate_local_revision
        validate_local_revision(data)


def get_revision(db, campaign_id, revision_id):
    header, _, _, _ = _context(db, campaign_id)
    row = db.get(GenesisWaterRevision, (campaign_id, revision_id))
    if row is None:
        raise ValueError("Missing W2 revision; refusing reconstruction")
    _validate_revision(row)
    if row.payload["signature"] != header.signature:
        raise ValueError("W2 revision belongs to another source authority")
    return {"revision_id": revision_id, "historical": True, "current_flow_authorization": False, "payload": deepcopy(row.payload)}


def get_water_domain(db, campaign_id, node):
    header, config, water, _ = _context(db, campaign_id)
    row = db.get(GenesisWaterDomain, (campaign_id, node))
    if row is None:
        raise ValueError("Prepare W2 domain explicitly")
    _validate_domain(row, header, opening_state(water, node))
    if row.state_version:
        revision = db.get(GenesisWaterRevision, (campaign_id, row.head_id))
        if revision is None:
            raise ValueError("W2 head revision disappeared")
        _validate_revision(revision)
        if checksum(revision.payload["after"].get(str(node))) != row.state_checksum:
            raise ValueError("W2 domain/head disagreement")
        if any(t["status"] == "applied" for t in revision.payload["transfers"]):
            _, statuses, _ = _read_evidence(db, campaign_id, revision.payload["evidence"].keys(), config)
            if any(v != "current" for v in statuses.values()):
                raise ValueError("W2 applied head has stale geometry; explicit future hold/revision required")
    return {"water_version": 2, "node": node, "head_id": row.head_id, "logical_minute": row.last_minute,
            "state": deepcopy(row.state), "state_checksum": row.state_checksum, "state_version": row.state_version,
            "authority": "W2_overlay_replaces_W1_checkpoint_for_this_domain", "prepared": True,
            "perennial": None, "state_is_not_mapped_water_occupation": True}


def query_water_state(db, campaign_id, node):
    """One quantity authority per domain; NEVER add W1 shadow and W2 together."""
    header, _, water, _ = _context(db, campaign_id)
    if db.get(GenesisWaterDomain, (campaign_id, node)) is not None:
        return get_water_domain(db, campaign_id, node)
    state = opening_state(water, node)
    return {"water_version": 2, "node": node, "prepared": False,
        "authority": "W1_checkpoint_reference_without_new_credit", "state": state,
        "state_checksum": checksum(state), "head_id": genesis_head(header.signature, node, state),
        "state_version": 0, "logical_minute": header.cutover_minute,
        "state_is_not_mapped_water_occupation": True, "perennial": None}
