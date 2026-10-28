"""Exact local ledger kernel. Physical admission is separate and fail-closed."""
from copy import deepcopy
from ..terrain.field import checksum
from ..water.balance import STORES


def opening_state(water, node):
    if type(node) is not int or not 0 <= node < len(water.hydrology.heights):
        raise ValueError("Invalid W2 H1 domain")
    last = water.solution.periods[-1]["stores"]
    return {"accounts": {f"w1:{name}": last[name][node] for name in STORES},
            "locations": {}, "opening_source": "W1_final_period_stocks_once",
            "origin_node": node, "permanent_waterbody": None}


def validate_state(state):
    if not isinstance(state.get("accounts"), dict) or not state["accounts"]:
        raise ValueError("W2 requires explicit accounts")
    if any(not isinstance(k, str) or type(v) is not int or v < 0 for k, v in state["accounts"].items()):
        raise ValueError("Invalid W2 quantized account")
    if not isinstance(state.get("locations"), dict):
        raise ValueError("Invalid W2 localization registry")


def genesis_head(signature, node, state):
    validate_state(state)
    return checksum(["w2-opening", signature, node, state])[:32]


def apply_batch(states, intents, admissions, period):
    """Admissions are produced internally by physical gates, NEVER client input.

    Batch oversubscription is rejected atomically, not resolved by exploration
    or lexicographic winner selection. Same-period receipts cannot be re-spent.
    """
    if type(period) is not int or period not in range(4):
        raise ValueError("Invalid W2 period")
    for state in states.values():
        validate_state(state)
    result = deepcopy(states)
    rows, debits, credits, edge_debits, edge_limits = [], {}, {}, {}, {}
    inputs = {node: 0 for node in states}
    outputs = {node: 0 for node in states}
    exports = {node: 0 for node in states}
    seen = set()
    for intent in sorted(intents, key=lambda i: i.transfer_id):
        if intent.transfer_id in seen:
            raise ValueError("Duplicated transfer in W2 batch")
        seen.add(intent.transfer_id)
        if intent.source_node not in states or intent.target_node is not None and intent.target_node not in states:
            raise ValueError("W2 transfer is outside its locked domains")
        source = states[intent.source_node]
        if intent.source_account not in source["accounts"]:
            raise ValueError("Unknown W2 source account")
        admission = admissions[intent.transfer_id]
        reasons = sorted(set(admission.get("reasons", [])))
        status = "pending"
        if intent.amount_liters == 0:
            status = "zero_request_no_transfer"
        elif source["accounts"][intent.source_account] == 0:
            reasons.append("source_account_dry")
        elif not source["locations"].get(intent.source_account) and not admission.get("conservative_localization_L1"):
            reasons.append("source_localization_pending")
        elif admission.get("status") == "admitted" and not reasons:
            cap = admission.get("capacity_liters")
            if type(cap) is not int or cap < intent.amount_liters:
                reasons.append("passage_capacity_insufficient")
            else:
                status = "applied"
                key = intent.source_node, intent.source_account
                debits[key] = debits.get(key, 0)+intent.amount_liters
                edge = admission["capacity_key"]
                if edge in edge_limits and edge_limits[edge] != cap:
                    raise ValueError("Conflicting W2 capacities for one physical passage")
                edge_limits[edge] = cap
                edge_debits[edge] = edge_debits.get(edge, 0)+intent.amount_liters
                if edge_debits[edge] > cap:
                    raise ValueError("W2 batch oversubscribes a shared passage")
                outputs[intent.source_node] += intent.amount_liters
                if intent.target_node is None:
                    if not admission.get("ocean_export_authorized"):
                        raise ValueError("W2 ocean export requires independent coastal proof")
                    exports[intent.source_node] += intent.amount_liters
                else:
                    key = intent.target_node, intent.target_account
                    credits[key] = credits.get(key, 0)+intent.amount_liters
                    inputs[intent.target_node] += intent.amount_liters
        rows.append({"transfer_id": intent.transfer_id, "status": status, "requested_liters": intent.amount_liters,
            "applied_liters": intent.amount_liters if status == "applied" else 0,
            "source_node": intent.source_node, "target_node": intent.target_node,
            "source_account": intent.source_account, "target_account": intent.target_account,
            "reasons": sorted(set(reasons)), "admission": deepcopy(admission)})
    for (node, account), amount in debits.items():
        if amount > states[node]["accounts"][account]:
            raise ValueError("W2 batch oversubscribes source stock")
        result[node]["accounts"][account] -= amount
    for (node, account), amount in credits.items():
        result[node]["accounts"][account] = result[node]["accounts"].get(account, 0)+amount
        # Receipt conserves quantity but does not invent exact downstream location.
    budgets = {}
    for node in states:
        before, after = sum(states[node]["accounts"].values()), sum(result[node]["accounts"].values())
        residual = before+inputs[node]-outputs[node]-after
        if residual:
            raise ValueError("W2 exact local conservation failure")
        budgets[node] = {"period": period, "start_storage_liters": before, "inputs_liters": inputs[node],
            "outputs_liters": outputs[node], "ocean_export_liters": exports[node],
            "end_storage_liters": after, "storage_delta_liters": after-before, "residual_liters": residual,
            "new_precipitation_liters": 0, "historical_W1_fluxes_recredited": False}
    if sum(b["start_storage_liters"] for b in budgets.values()) != sum(b["end_storage_liters"]+b["ocean_export_liters"] for b in budgets.values()):
        raise ValueError("W2 batch conservation failure")
    return result, rows, budgets
