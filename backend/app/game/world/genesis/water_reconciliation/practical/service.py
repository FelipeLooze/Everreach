"""P1 extends the W2 ledger with normalized child accounts; no second water total."""
from copy import deepcopy
import json
from sqlalchemy import update
from app.db.models.world_practical_hydrology import GenesisPracticalHydrology, GenesisLocalWaterAccount, GenesisPracticalCapacityUse
from app.db.models.world_hydro_geometry import GenesisHydroGeometryEvidence
from app.db.models.world_water_reconciliation import (GenesisWaterReconciliation, GenesisWaterDomain,
    GenesisWaterRevision, GenesisWaterTransfer, GenesisWaterReconciliationEvidence)
from ...terrain.field import checksum
from ...sphere_topology import SurfacePoint
from ...hydro_geometry.config import Anchor, GeometryRequest
from ...hydro_geometry.service import materialize_geometry, get_geometry
from ...hydro_geometry.spatial import probe_arc_upper_mm
from ..ledger import apply_batch, opening_state
from ..config import TransferIntent
from ..events import event_snapshot
from .config import PracticalConfig
from .allocation import surface_quota
from .hydraulics import capacity, transverse_points

POOL = "p1:allocated_surface"


def _context(db, campaign_id):
    from ..service import _context as w2_context
    header, wconfig, water, g1 = w2_context(db, campaign_id)
    row = db.get(GenesisPracticalHydrology, campaign_id)
    if row is None:
        raise ValueError("Initialize P1 explicitly; existing water authorities are not upgraded")
    config = PracticalConfig.model_validate(row.config)
    expected = checksum(["practical-hydrology-p1", header.signature, config.model_dump()])[:24]
    if type(row.practical_version) is not int or row.practical_version != 1 or row.source_signature != header.signature or row.signature != expected:
        raise ValueError("P1 version/source/configuration mismatch")
    return header, wconfig, water, g1, row, config


def initialize_practical_hydrology(db, campaign_id, config=None):
    from ..service import _context as w2_context
    header, _, _, _ = w2_context(db, campaign_id)
    row = db.get(GenesisPracticalHydrology, campaign_id)
    if row is not None:
        _, _, _, _, row, pinned = _context(db, campaign_id)
        if config is not None and config != pinned:
            raise ValueError("Cannot silently reconfigure P1")
        return row
    if db.query(GenesisWaterDomain.node).filter_by(campaign_id=campaign_id).first() is not None:
        raise ValueError("P1 requires a new W2 authority with no prepared domains; old saves need an explicit migration")
    config = config or PracticalConfig()
    row = GenesisPracticalHydrology(campaign_id=campaign_id, practical_version=1, source_signature=header.signature,
        config=config.model_dump(), signature=checksum(["practical-hydrology-p1", header.signature, config.model_dump()])[:24])
    db.add(row)
    db.flush()
    return row


def local_account_id(signature, proof, vertex):
    return "l1:"+checksum([signature, proof["allocation"]["tile"], vertex])[:32]


def wet_account_id(signature, proof):
    return "k1:"+checksum([signature, proof["points"][0], proof["points"][-1]])[:32]


def validate_proof(proof, config, water, terrain_signature):
    raw = {k: v for k, v in proof.items() if k != "proof_id"}
    if (proof.get("kind") != "natural_passage_k1" or type(proof.get("practical_version")) is not int or proof.get("practical_version") != 1 or
            type(proof.get("capacity_version")) is not int or proof.get("capacity_version") != 1 or proof.get("proof_id") != checksum(raw)[:32] or
            proof.get("terrain_signature") != terrain_signature or proof.get("w1_signature") != water.signature or
            proof.get("config") != config.model_dump() or proof.get("terrain_modified") is not False):
        raise ValueError("Invalid P1 proof/version/source checksum")
    from ...terrain.address import TerrainTile
    quota = surface_quota(water, TerrainTile(*proof["allocation"]["tile"]), config)
    if quota != proof["allocation"]:
        raise ValueError("L1 quota was not derived from its historical source")
    a, b = proof["source_vertex"], proof["target_vertex"]
    n = config.grid_intervals
    if (not 0 < a < (n+1)**2 or not 0 < b < (n+1)**2 or abs(a-b) not in (1, n+1) or
            any(not 2 <= v%(n+1) < n-1 or not 2 <= v//(n+1) < n-1 for v in (a, b))):
        raise ValueError("P1 prototype requires two internal adjacent finite-volume cells")
    from ...terrain.address import TerrainTile
    tile = TerrainTile(*quota["tile"])
    if (proof["points"][0] != list(tile.point(a%(n+1), a//(n+1), n).xyz) or
            proof["points"][-1] != list(tile.point(b%(n+1), b//(n+1), n).xyz)):
        raise ValueError("L1 source/receiver supports do not match their coordinates")
    interface = proof["shared_interface"]
    left, right = interface["source_view"], interface["receiver_view"]
    if (any(left[k] != right[k] for k in ("id", "point", "terrain_mm", "head_mm")) or
            left["point"] != list(tile.point(a%(n+1)+b%(n+1), a//(n+1)+b//(n+1), n*2).xyz) or
            left["head_mm"] < left["terrain_mm"] or
            not proof["head_profile_reference_mm"][0] >= left["head_mm"] >= proof["head_profile_reference_mm"][-1]):
        raise ValueError("K1 bilateral interface conditions disagree")
    depth = proof["capacity"]["depth_mm"]
    if proof["source_reserve_liters"] != (depth*quota["vertex_areas_mm2"][a]+10**6-1)//10**6:
        raise ValueError("K1 inlet reserve is not supported by its allocated area")
    probes = [SurfacePoint(*p) for p in proof["points"]]
    if len(proof["cross_sections"]) != 5:
        raise ValueError("K1 requires a section at every longitudinal probe")
    for i, section in enumerate(proof["cross_sections"]):
        expected_points = transverse_points(probes[i], probes[min(4, i+1)] if i < 4 else probes[3], water.hydrology.radius_m, config)
        if expected_points is None or section["points"] != [list(p.xyz) for p in expected_points]:
            raise ValueError("K1 transverse sampling footprint was altered")
        zs = section["terrain_mm"]
        m = len(zs)//2
        if section["bank_room_mm"] != min(max(zs[:m]), max(zs[m+1:]))-zs[m]:
            raise ValueError("K1 bank/overflow height was altered")
    heights = proof["terrain_profile_mm"]
    if len(heights) != 5 or heights[0] <= heights[-1] or any(v > u for u, v in zip(heights, heights[1:])):
        raise ValueError("K1 cannot authorize an uphill natural path")
    expected = capacity(proof["cross_sections"], [SurfacePoint(*p) for p in proof["points"]], heights,
        proof["capacity"]["depth_mm"], proof["head_profile_reference_mm"][0]-proof["head_profile_reference_mm"][-1],
        {"radius_m": water.hydrology.radius_m, "policy": config})
    if expected != proof["capacity"] or expected["episode_capacity_liters"] <= 0:
        raise ValueError("K1 capacity is not supported by its section/slope model")


def prepare_natural_passage(db, campaign_id, proof):
    header, wconfig, water, g1, policy, config = _context(db, campaign_id)
    validate_proof(proof, config, water, g1.terrain.signature)
    key = "p1:"+checksum([policy.signature, proof["proof_id"]])[:32]
    existing = db.get(GenesisWaterReconciliationEvidence, (campaign_id, key))
    if existing is not None:
        read_current(db, campaign_id, existing)
        return existing
    from ...terrain.service import get_terrain_sampler
    sampler = get_terrain_sampler(db, campaign_id)
    for point, z in zip(proof["points"], proof["terrain_profile_mm"]):
        if sampler.sample(SurfacePoint(*point))["height_mm"] != z:
            raise ValueError("K1 longitudinal samples do not match real T1")
    interface = proof["shared_interface"]["source_view"]
    if sampler.sample(SurfacePoint(*interface["point"]))["height_mm"] != interface["terrain_mm"]:
        raise ValueError("K1 interface does not match authoritative T1")
    for section in proof["cross_sections"]:
        if [sampler.sample(SurfacePoint(*p))["height_mm"] for p in section["points"]] != section["terrain_mm"]:
            raise ValueError("K1 cross sections do not match real T1")
    source = local_account_id(policy.signature, proof, proof["source_vertex"])
    target = local_account_id(policy.signature, proof, proof["target_vertex"])
    request = GeometryRequest(tile=proof["allocation"]["tile"], grid_intervals=config.grid_intervals,
        target_spacing_m=1, anchors=[Anchor(id=source, point=proof["points"][0], role="ingress"),
                                  Anchor(id=target, point=proof["points"][-1], role="outlet")],
        provenance={"local_water_policy": "L1", "no_new_spring": True})
    saved = materialize_geometry(db, campaign_id, request)
    route = next((r for r in saved.baseline["routes"] if r["source_anchor_id"] == source), None)
    if route is None or route["status"] != "verified_at_requested_resolution" or route["terrain_profile_mm"] != proof["terrain_profile_mm"]:
        raise ValueError("G1 did not verify the measured internal natural passage")
    data = {"kind": "practical_evidence_p1", "practical_version": 1, "policy_signature": policy.signature,
        "w2_signature": header.signature, "proof": proof, "g1_request_id": saved.request_id,
        "g1_checksum": saved.baseline_checksum, "source_account": source, "target_account": target,
        "wetting_account": wet_account_id(policy.signature, proof),
        "claim": "model_uniform_surface_film_not_exact_historical_water_location",
        "terrain_modified": False, "ocean_export_authorized": False}
    row = GenesisWaterReconciliationEvidence(campaign_id=campaign_id, evidence_key=key, kind="p1",
        node=proof["allocation"]["source_node"], baseline=data, checksum=checksum(data))
    db.add(row)
    db.flush()
    read_current(db, campaign_id, row)
    return row


def read_current(db, campaign_id, row):
    header, wconfig, water, g1, policy, config = _context(db, campaign_id)
    if row.kind != "p1" or checksum(row.baseline) != row.checksum:
        raise ValueError("P1 evidence checksum mismatch")
    data = row.baseline
    if (type(data.get("practical_version")) is not int or data["practical_version"] != 1 or
            data["policy_signature"] != policy.signature or data["w2_signature"] != header.signature):
        raise ValueError("P1 evidence belongs to another authority")
    validate_proof(data["proof"], config, water, g1.terrain.signature)
    tracked = db.get(GenesisHydroGeometryEvidence, (campaign_id, data["g1_request_id"]))
    if tracked is not None and tracked not in db.dirty and tracked not in db.new:
        db.refresh(tracked)
    historical = get_geometry(db, campaign_id, data["g1_request_id"], baseline_only=True)
    if historical["baseline_checksum"] != data["g1_checksum"]:
        raise ValueError("P1 pinned G1 baseline changed")
    # K1 has complete local sections; G1's unrelated 100 m diagnostic transects
    # are not silently substituted for this smaller versioned proof domain.
    local_geometry = {**historical["baseline"], "terrain_coverage": data["proof"]["terrain_coverage"]}
    events = event_snapshot(db, campaign_id, local_geometry, wconfig.max_event_rows)
    return historical["baseline"], events, "current" if events["current"] else "invalidated"


def _validate_account(row, db=None):
    if (checksum(row.origin) != row.origin_checksum or checksum(row.balance) != row.state_checksum or
            type(row.balance.get("liters")) is not int or row.balance["liters"] < 0):
        raise ValueError("P1 child account integrity failure")
    if db is not None:
        from ..service import _validate_revision
        revision = db.get(GenesisWaterRevision, (row.campaign_id, row.head_id))
        if revision is None:
            raise ValueError("P1 child-account head disappeared")
        _validate_revision(revision)
        if revision.payload.get("local_reconciliation", {}).get("after", {}).get(row.account_id) != row.balance["liters"]:
            raise ValueError("P1 child balance disagrees with its immutable revision")


def _origins(data, policy):
    proof, output = data["proof"], {}
    quota = proof["allocation"]
    for field, vertex, point in (("source_account", proof["source_vertex"], proof["points"][0]),
                                 ("target_account", proof["target_vertex"], proof["points"][-1])):
        identifier = local_account_id(policy.signature, proof, vertex)
        if data[field] != identifier:
            raise ValueError("P1 noncanonical account ID")
        output[identifier] = {"kind": "L1_surface_dual_cell", "policy_signature": policy.signature,
            "source_node": quota["source_node"], "source_account": "w1:surface", "parcel": quota["tile"],
            "vertex": vertex, "point": point, "area_mm2": quota["vertex_areas_mm2"][vertex],
            "initial_quota_liters": quota["vertex_quota_liters"][vertex], "permanent_waterbody": None}
    return output


def reconcile_practical(db, campaign_id, request):
    from ..service import _validate_domain, _validate_revision
    header, wconfig, water, g1, policy, config = _context(db, campaign_id)
    if len(request.transfers) != 1 or len(request.expected_heads) != 1 or db.get_bind().dialect.name != "sqlite":
        raise ValueError("P1 prototype reconciles one local passage and one W2 parent per explicit SQLite revision")
    intent = request.transfers[0]
    if len(intent.evidence_keys) != 1:
        raise ValueError("P1 requires one versioned local proof")
    if set(request.evidence_keys)-set(intent.evidence_keys):
        raise ValueError("P1 will not silently ignore unrelated revision evidence")
    evidence = db.get(GenesisWaterReconciliationEvidence, (campaign_id, intent.evidence_keys[0]))
    if evidence is None or evidence.kind != "p1":
        raise ValueError("Missing P1 evidence")
    request_hash = checksum(request.canonical())
    db.execute(update(GenesisWaterReconciliation).where(GenesisWaterReconciliation.campaign_id == campaign_id,
        GenesisWaterReconciliation.signature == header.signature).values(write_epoch=GenesisWaterReconciliation.write_epoch+1),
        execution_options={"synchronize_session": False})
    db.flush()
    with db.begin_nested():
        previous = db.query(GenesisWaterRevision).filter_by(campaign_id=campaign_id, operation_id=request.operation_id).first()
        if previous is not None:
            if previous.request_checksum != request_hash:
                raise ValueError("P1 operation ID reused with a different intent")
            _validate_revision(previous)
            return previous
        geometry, events, status = read_current(db, campaign_id, evidence)
        if status != "current":
            raise ValueError("P1 geometry invalidated by events; balances and history retained")
        data, node = evidence.baseline, evidence.node
        proof = data["proof"]
        if (intent.source_node != node or intent.target_node != node or set(request.expected_heads) != {str(node)} or
                intent.coast_evidence_key is not None):
            raise ValueError("P1 does not authorize cross-region or ocean transfer")
        domain = db.get(GenesisWaterDomain, (campaign_id, node), populate_existing=True)
        if domain is None:
            raise ValueError("Prepare the W2 parent domain explicitly")
        _validate_domain(domain, header, opening_state(water, node))
        if domain.head_id != request.expected_heads[str(node)] or request.logical_minute < domain.last_minute:
            raise ValueError("Stale P1 parent head or logical time")
        origins = _origins(data, policy)
        child_rows = {}
        for identifier in origins:
            account = db.get(GenesisLocalWaterAccount, (campaign_id, identifier), populate_existing=True)
            if account is not None:
                _validate_account(account, db)
                if account.origin != origins[identifier]:
                    raise ValueError("L1 allocation origin changed")
                child_rows[identifier] = account
        before = deepcopy(domain.state)
        period = ((request.logical_minute-header.cutover_minute)*4//(water.year_days*1440))%4
        capacity_key = None
        if intent.source_account == "w1:surface" and intent.target_account == POOL:
            pending = {k: v for k, v in origins.items() if k not in child_rows}
            amount = sum(v["initial_quota_liters"] for v in pending.values())
            if not pending or intent.amount_liters != amount or amount <= 0:
                raise ValueError("L1 claims must debit only the exact not-yet-localized area quotas")
            admission = {intent.transfer_id: {"status": "admitted", "reasons": [], "capacity_liters": amount,
                "capacity_key": "L1:"+evidence.evidence_key, "conservative_localization_L1": True,
                "quantity_operation": "spatial_allocation_not_water_flow", "ocean_export_authorized": False}}
            after, transfers, budgets = apply_batch({node: before}, [intent], admission, period)
            after[node]["locations"][POOL] = {"authority": policy.signature, "kind": "aggregate_of_normalized_children_not_an_extra_stock"}
            local_before = {k: 0 for k in pending}
            local_after = {k: v["initial_quota_liters"] for k, v in pending.items()}
            local = {"kind": "L1_allocation", "before": local_before, "after": local_after,
                "parent_debit_liters": amount, "child_credit_liters": sum(local_after.values()), "residual_liters": 0}
            transfers[0]["quantity_operation"] = "spatial_allocation_not_water_flow"
            updates = {k: (origins[k], value) for k, value in local_after.items()}
        else:
            if intent.source_account != data["source_account"] or intent.target_account != data["target_account"]:
                raise ValueError("K1 intent does not match its verified local cells")
            if len(child_rows) != 2:
                raise ValueError("Localize the L1 source/receiver quotas before requesting flow")
            source, target = child_rows[data["source_account"]], child_rows[data["target_account"]]
            wet_id = data["wetting_account"]
            wet = db.get(GenesisLocalWaterAccount, (campaign_id, wet_id), populate_existing=True)
            if wet:
                _validate_account(wet, db)
            start = request.logical_minute-config.episode_minutes
            if start < header.cutover_minute or any(r.last_minute > start for r in child_rows.values()):
                raise ValueError("P1 episode overlaps an already consolidated local state")
            capacity_key = checksum(["K1-window", policy.signature, proof["points"][0], proof["points"][-1], start, request.logical_minute])[:32]
            if db.get(GenesisPracticalCapacityUse, (campaign_id, capacity_key)) is not None:
                raise ValueError("K1 passage capacity was already used for this episode")
            a, b = source.balance["liters"], target.balance["liters"]
            hold = wet.balance["liters"] if wet else 0
            fill = max(0, proof["capacity"]["required_wetting_liters"]-hold)
            target_origin = origins[data["target_account"]]
            dest_depth = ((b+intent.amount_liters)*10**6+target_origin["area_mm2"]-1)//target_origin["area_mm2"]
            heads = [z+proof["capacity"]["depth_mm"] for z in proof["terrain_profile_mm"]]
            heads[-1] = proof["terrain_profile_mm"][-1]+dest_depth
            if (intent.amount_liters <= 0 or a-fill-intent.amount_liters < proof["source_reserve_liters"] or
                    dest_depth >= proof["cross_sections"][-1]["bank_room_mm"] or any(u < v for u, v in zip(heads, heads[1:]))):
                raise ValueError("K1 source reserve, receiver containment or head condition is not satisfied; retain excess")
            estimate = capacity(proof["cross_sections"], [SurfacePoint(*p) for p in proof["points"]], proof["terrain_profile_mm"],
                proof["capacity"]["depth_mm"], heads[0]-heads[-1], {"radius_m": water.hydrology.radius_m, "policy": config})
            if estimate is None or fill+intent.amount_liters > estimate["episode_capacity_liters"]:
                raise ValueError("K1 model capacity exceeded; no unsupported overflow or inundation is created")
            accounts = {data["source_account"]: a, data["target_account"]: b, wet_id: hold}
            child_state = {"accounts": accounts, "locations": {k: {"proof": evidence.evidence_key} for k in accounts}}
            movements = [intent]
            if fill:
                movements.insert(0, TransferIntent(transfer_id="wet:"+checksum([intent.transfer_id, capacity_key])[:32],
                    source_node=node, target_node=node, source_account=data["source_account"], target_account=wet_id,
                    amount_liters=fill, evidence_keys=intent.evidence_keys))
            admissions = {t.transfer_id: {"status": "admitted", "reasons": [], "capacity_liters": estimate["episode_capacity_liters"],
                "capacity_key": capacity_key, "model": "K1", "scientific_certification": False, "ocean_export_authorized": False} for t in movements}
            child_after, transfers, budgets = apply_batch({node: child_state}, movements, admissions, period)
            after = {node: deepcopy(before)}  # Internal child transfers conserve the parent aggregate.
            parent_total = sum(before["accounts"].values())
            budgets[node].update(start_storage_liters=parent_total, end_storage_liters=parent_total, storage_delta_liters=0)
            local = {"kind": "K1_flow", "before": accounts, "after": child_after[node]["accounts"],
                "residual_liters": 0, "capacity": estimate, "capacity_key": capacity_key,
                "episode_start_minute": start, "episode_end_minute": request.logical_minute,
                "wetting_liters": fill, "delivered_liters": intent.amount_liters}
            local["execution_dependency"] = "fill_reach_storage_before_delivering_downstream_no_reuse_of_wetting_water"
            wet_origin = {"kind": "K1_reach_wetting", "policy_signature": policy.signature, "source_node": node,
                "point": proof["points"][2], "geometry_capacity_liters": proof["capacity"]["required_wetting_liters"], "permanent_waterbody": None}
            all_origins = {**origins, wet_id: wet_origin}
            updates = {k: (all_origins[k], v) for k, v in local["after"].items()}
        payload = {"kind": "water_revision_w2", "water_version": 2, "signature": header.signature,
            "request": request.canonical(), "previous_heads": request.expected_heads, "logical_minute": request.logical_minute,
            "period": period, "sources": header.sources, "evidence": {evidence.evidence_key: {"status": status,
                "checksum": evidence.checksum, "g1_request_id": data["g1_request_id"], "events": events}},
            "coastal_evidence": {}, "before": {str(node): before}, "after": {str(node): after[node]},
            "budgets": {str(node): budgets[node]}, "transfers": transfers, "evidence_assessments": {},
            "local_reconciliation": local, "policy_extension": {"kind": "P1", "version": 1, "signature": policy.signature},
            "baseline_W1_mutated": False, "perennial": None}
        if len(json.dumps(payload, separators=(",", ":")).encode()) > wconfig.max_payload_bytes:
            raise ValueError("P1 W2 revision payload budget exceeded")
        rid = checksum(["w2-revision", payload])[:32]
        applied_ids = [t["transfer_id"] for t in transfers if t["status"] == "applied"]
        if db.query(GenesisWaterTransfer.transfer_id).filter(GenesisWaterTransfer.campaign_id == campaign_id,
                GenesisWaterTransfer.transfer_id.in_(applied_ids)).first():
            raise ValueError("P1 transfer already applied")
        revision = GenesisWaterRevision(campaign_id=campaign_id, revision_id=rid, operation_id=request.operation_id,
            request_checksum=request_hash, payload_checksum=checksum(payload), logical_minute=request.logical_minute,
            period=period, payload=payload)
        db.add(revision)
        db.flush()
        changed = db.execute(update(GenesisWaterDomain).where(GenesisWaterDomain.campaign_id == campaign_id,
            GenesisWaterDomain.node == node, GenesisWaterDomain.head_id == request.expected_heads[str(node)],
            GenesisWaterDomain.state_version == domain.state_version).values(state=after[node], state_checksum=checksum(after[node]),
                head_id=rid, state_version=domain.state_version+1, last_minute=request.logical_minute),
                execution_options={"synchronize_session": False})
        if changed.rowcount != 1:
            raise ValueError("Concurrent P1 parent change")
        db.expire(domain)
        for identifier, (origin, amount) in updates.items():
            account = db.get(GenesisLocalWaterAccount, (campaign_id, identifier))
            if account is None:
                db.add(GenesisLocalWaterAccount(campaign_id=campaign_id, account_id=identifier, node=node, origin=origin,
                    origin_checksum=checksum(origin), balance={"liters": amount}, state_checksum=checksum({"liters": amount}),
                    state_version=0, head_id=rid, last_minute=request.logical_minute))
            else:
                _validate_account(account, db)
                if account.origin != origin:
                    raise ValueError("P1 account origin cannot be reinterpreted")
                account.balance = {"liters": amount}
                account.state_checksum = checksum(account.balance)
                account.state_version += 1
                account.head_id, account.last_minute = rid, request.logical_minute
        for transfer in transfers:
            db.add(GenesisWaterTransfer(campaign_id=campaign_id, transfer_id=transfer["transfer_id"], revision_id=rid, payload=transfer))
        if capacity_key is not None:
            db.add(GenesisPracticalCapacityUse(campaign_id=campaign_id, capacity_key=capacity_key, revision_id=rid, payload=local))
        db.flush()
        _validate_revision(revision)
        validate_local_revision(payload)
        return revision


def validate_local_revision(payload):
    extension = payload.get("policy_extension", {})
    if extension.get("kind") != "P1" or type(extension.get("version")) is not int or extension["version"] != 1:
        raise ValueError("Unsupported P1 ledger extension version")
    local = payload["local_reconciliation"]
    if local.get("kind") not in ("L1_allocation", "K1_flow"):
        raise ValueError("Unsupported P1 local operation")
    if any(type(v) is not int or v < 0 for field in ("before", "after") for v in local[field].values()):
        raise ValueError("Invalid P1 local quantity")
    delta = sum(local["after"].values())-sum(local["before"].values())
    if local["residual_liters"] != 0 or delta != (local["parent_debit_liters"] if local["kind"] == "L1_allocation" else 0):
        raise ValueError("P1 hierarchical conservation failed")
    node = next(iter(payload["before"]))
    before, after = payload["before"][node]["accounts"], payload["after"][node]["accounts"]
    if local["kind"] == "L1_allocation":
        if (before["w1:surface"]-after["w1:surface"] != delta or
                after.get(POOL, 0)-before.get(POOL, 0) != delta or local["child_credit_liters"] != delta):
            raise ValueError("L1 parent debit and normalized child credit disagree")
    else:
        reconstructed = dict(local["before"])
        for transfer in payload["transfers"]:
            reconstructed[transfer["source_account"]] -= transfer["applied_liters"]
            reconstructed[transfer["target_account"]] += transfer["applied_liters"]
        if reconstructed != local["after"] or before != after:
            raise ValueError("K1 child transfers or parent aggregate were duplicated")
        if sum(t["applied_liters"] for t in payload["transfers"]) > local["capacity"]["episode_capacity_liters"]:
            raise ValueError("K1 wetting and flow exceeded the same episode capacity")


def get_local_account(db, campaign_id, identifier):
    _context(db, campaign_id)
    row = db.get(GenesisLocalWaterAccount, (campaign_id, identifier))
    if row is None:
        raise ValueError("Missing local account; no implicit localization")
    _validate_account(row, db)
    return {"account_id": identifier, "node": row.node, "origin": deepcopy(row.origin), "liters": row.balance["liters"],
        "head_id": row.head_id, "last_minute": row.last_minute, "quantity_is_part_of_W2_parent_pool": True,
        "perennial": None, "mapped_inundation_claimed": False, "flow_authorization_from_quantity": False}
