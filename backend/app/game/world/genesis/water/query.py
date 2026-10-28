"""Read-only quantities. Repeated map fragments are throughput views, not new water."""
from ..formation_plan import cell_index
from ..sphere_topology import cell_at
from ..hydrology.regional import regional_sector_snapshot
from .balance import STORES
from .plan import checksum


def regime(volumes, year_days, threshold):
    present = sum(v > 0 and v*4 >= threshold*year_days*86400 for v in volumes)
    if not present:
        return "trace_below_reporting_threshold" if any(volumes) else "potentially_dry"
    return "regularly_supplied_in_model_window" if present == 4 else "temporary" if present == 1 else "seasonal"


def node_record(plan, node):
    if type(node) is not int or not 0 <= node < len(plan.hydrology.heights):
        raise ValueError("Invalid W1 macro node")
    periods = []
    for index, period in enumerate(plan.solution.periods):
        flux = {k+"_liters": values[node] for k, values in period["fluxes"].items()}
        stores = {k+"_liters": values[node] for k, values in period["stores"].items()}
        periods.append({"index": index, "duration_days": [plan.year_days, 4], **flux,
            "stores": stores, "mean_discharge_m3_s_rational": [flux["outflow_liters"]*4, plan.year_days*86400*1000]})
    if plan.config.source_climate_version==3:
        for index,period in enumerate(periods):
            recycled=0 if plan.hydrology.drainage.marine[node] else plan.atmospheric_recycling_mm[index][node]*plan.hydrology.cell_area_m2[node]
            net=0 if plan.hydrology.drainage.marine[node] else plan.atmospheric_net_deposition_mm[index][node]*plan.hydrology.cell_area_m2[node]
            period.update(atmospheric_recycling_potential_liters=recycled,atmospheric_net_deposition_diagnostic_liters=net,
                model_ET_shortfall_to_atmospheric_hypothesis_liters=max(0,recycled-period['evapotranspiration_liters']),
                atmospheric_recycling_credited_to_stock=False,forcing_contract=plan.config.forcing_contract)
    outflows = [p["outflow_liters"] for p in periods]
    local = [p["local_runoff_liters"] for p in periods]
    h1 = plan.hydrology
    proof = plan.support[node] == "bilateral_downhill_validated"
    return {"id": plan.identifier("node", node), "node": node, "water_version": 1,
        "macro_area_m2": h1.cell_area_m2[node],
        "signature": plan.signature, "h1_basin_id": h1.identifier("basin", h1.drainage.outlet[node]),
        "h1_raw_terminal_id": h1.identifier("raw-terminal", h1.drainage.raw_outlet[node]),
        "route_status": plan.support[node], "local_supply_regime": regime(local, plan.year_days, plan.config.flow_presence_liters_per_second),
        "routed_regime": regime(outflows, plan.year_days, plan.config.flow_presence_liters_per_second) if proof else "pending_or_terminal",
        "model_fed_sampled_corridor": proof and any(outflows),
        "local_runoff_is_not_automatically_a_river": True, "perennial": None, "river_bed_geometry_final": False,
        "conveyance_capacity_validated": False, "routing_assumption": "lumped_unconstrained_conveyance",
        "column_storage_reference_liters": plan.capacities_liters[node],
        "capacity_model": "h1_center_column_prism_not_connected_lake_bathymetry",
        "lake_permanent": None, "lake_geometry": None, "flooded_area": None,
        "storage_condition": "water_in_approximate_column" if any(p["stores"]["depression_liters"] for p in periods) else "no_column_water_in_model_window",
        "snow_storage_delta_liters": periods[-1]["stores"]["snow_liters"]-plan.solution.initial_stores[0][node],
        "unresolved_is_unallocated_accounting_not_a_lake": True, "periods": periods}


def point_record(plan, point):
    record = node_record(plan, cell_index(cell_at(point, plan.hydrology.config.level)))
    return {**record, "point": list(point.xyz), "coverage": "macro_cell_quantity_not_point_depth"}


def boundary_record(plan, source):
    node = node_record(plan, source)
    h1, parent = plan.hydrology, plan.hydrology.drainage.parent[source]
    if parent < 0:
        raise ValueError("Terminal has no water transfer boundary")
    reach = h1.reaches[h1.channel_index[source]] if source in h1.channel_index else None
    return {"id": plan.identifier("boundary", source), "source_node": source, "target_node": parent,
        "h1_reach_id": h1.identifier("reach", reach.start) if reach else None,
        "whole_reach_geometry_validated": bool(reach) and all(plan.support[n] == "bilateral_downhill_validated" for n in reach.nodes[:-1]),
        "hr1_port_id": plan.port_ids[source], "status": plan.support[source],
        "period_transfer_liters": [p["outflow_liters"] for p in node["periods"]],
        "model_fed_sampled_corridor": node["model_fed_sampled_corridor"], "perennial": None}


def regional_sector_record(plan, key, region=None):
    node = cell_index(key.parent(plan.hydrology.config.level)) if key.level >= plan.hydrology.config.level else None
    if node is None:
        raise ValueError("W1 local query must refine one canonical H1 cell")
    records, boundaries = [], []
    manifest = dict(plan.manifest)
    if region is not None:
        if region["node"] != node or checksum(region) != manifest.get(node):
            raise ValueError("Regional geometry is not in the fixed W1 evidence manifest")
        segment_volumes = {s["id"]: [0]*4 for s in region["segments"]}
        for route in region["routes"]:
            port = next(p for p in region["ports"] if p["id"] == route["port_id"])
            source = port["source_node"]
            boundary = boundary_record(plan, source)
            boundaries.append(boundary)
            if plan.support[source] == "bilateral_downhill_validated":
                for sid in set(route["segment_ids"]):
                    for season, amount in enumerate(boundary["period_transfer_liters"]):
                        segment_volumes[sid][season] += amount
        for piece in regional_sector_snapshot(region, key)["pieces"]:
            volumes = segment_volumes[piece["segment_id"]]
            records.append({**piece, "water_segment_id": plan.identifier("segment", piece["segment_id"]),
                "period_throughput_liters": volumes,
                "model_fed_sampled_segment": any(volumes),
                "modeled_wet_state": "water_transferred" if any(volumes) else "no_confirmed_transfer",
                "regime": regime(volumes, plan.year_days, plan.config.flow_presence_liters_per_second),
                "quantity_semantics": "throughput_view_do_not_sum_repeated_fragments", "perennial": None})
    candidates = [{"hr1_candidate_id": c["id"], "water_allocation_liters": None, "permanent": None,
                   "status": "needs_local_capacity_and_terrain_refinement"} for c in region["depression_candidates"]] if region else []
    return {"water_version": 1, "signature": plan.signature, "sector": [key.face, key.level, key.x, key.y],
        "macro": node_record(plan, node), "boundaries": boundaries, "segments": records,
        "regional_depression_candidates": candidates,
        "local_geometry_status": "fixed_hr1_evidence" if region is not None else "regional_evidence_pending",
        "river_bed_geometry_final": False}
