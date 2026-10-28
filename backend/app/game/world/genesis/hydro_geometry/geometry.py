"""G1 evidence preparation. No water volumes or terrain heights are rewritten."""
import json
from ..formation_tectonics import evaluate
from ..sphere_topology import SurfacePoint
from ..terrain.address import TerrainTile
from ..terrain.field import checksum
from .config import GeometryRequest
from .graph import SampleContext, BudgetExhausted, ResolutionRequired, build_graph, directed, flood, path_to
from .sections import sample_section
from .depressions import investigate
from .spatial import distance_mm, probe_arc_upper_mm, coverage_boxes


def request_id(plan, request):
    return checksum(["g1-request", plan.signature, request.canonical()])[:32]


def coastal_evidence(sampler, graph):
    source, records = sampler.plan.source, []
    counts = {"inspected_near_datum": 0, "legacy_t1_disagreements": 0}
    datum = source.config.sea_level_m*1000
    for p, height in zip(graph.points, graph.heights):
        if abs(height-datum) > 500_000:
            continue
        raw = evaluate(source.seed, source.config, source.plates, p, causes=False)["elevation_m"]*1000
        counts["inspected_near_datum"] += 1
        if (raw >= datum) != (height >= datum):
            counts["legacy_t1_disagreements"] += 1
            records.append({"point": list(p.xyz), "v4_height_mm": raw, "t1_height_mm": height,
                "r1_macro_component_id": source.component_at(p).id,
                "status": "legacy_t1_datum_disagreement_requires_versioned_coast_evidence"})
    return {"coast_policy_version": 1, "datum_mm": datum, **counts, "mismatches": records,
        "local_classification": "T1_height_relative_to_datum",
        "below_datum_does_not_prove_ocean_connectivity": True, "ocean_export_authorized": False,
        "legacy_v4_r1_labels_preserved": True, "global_coast_reconciliation": "pending"}


def build_geometry(plan, sampler, request):
    if sampler.plan.signature != plan.terrain.signature:
        raise ValueError("G1 sampler is not the pinned T1 authority")
    request = GeometryRequest.model_validate(request.canonical())
    config, tile = plan.config, TerrainTile(*request.tile)
    if tile.level < plan.hydrology.config.level:
        raise ValueError("G1 domain must be inside one H1 physical region")
    if request.sample_budget > config.max_samples or request.expansion_budget > config.max_expansions:
        raise ValueError("G1 request exceeds pinned processing limits")
    rid = request_id(plan, request)
    result = {"kind": "hydro_geometry_evidence_g1", "geometry_version": 1, "signature": plan.signature,
        "hydrology_signature": plan.hydrology.signature, "hydrology_checksum": plan.hydrology_checksum,
        "hr_signature": plan.hr_signature,
        "terrain_signature": plan.terrain.signature, "request_id": rid, "request": request.canonical(),
        "grid_spacing_upper_bound_m": (2*plan.hydrology.radius_m+request.grid_intervals*2**tile.level-1)//(request.grid_intervals*2**tile.level),
        "status": "pending_budget", "routes": [], "segments": [], "confluences": [], "sections": [],
        "graph": None, "depression_geometry": {"status": "not_inspected", "depressions": []},
        "coast": None, "issues": [], "terrain_modified": False, "water_ledger_modified": False,
        "terrain_baseline_only": True, "terrain_event_epoch": "unmodified_baseline",
        "distance_method": "integer_chord_lengths_with_guarded_arc_probe_bounds", "angular_precision_bits": 50,
        "active_watercourses": [], "water_volume_liters": None, "permanent": None,
        "guarantee": "sampled_geometry_at_declared_spacing_not_continuous_hydraulic_proof"}
    upstream_samples = request.provenance.get("port_search_samples", 0)
    if type(upstream_samples) is not int or not 0 <= upstream_samples < request.sample_budget:
        raise ValueError("Invalid G1 upstream selection budget")
    context = SampleContext(sampler, request.sample_budget-upstream_samples)
    expansions = 0
    try:
        graph = build_graph(context, tile, request.grid_intervals, request.anchors, plan.hydrology.radius_m)
        radius = plan.hydrology.radius_m
        result["graph"] = {"points": [list(p.xyz) for p in graph.points], "heights_mm": graph.heights,
            "edges": [[a, b, max(profile[1])] for (a, b), profile in sorted(graph.profiles.items())],
            "boundary_vertices": sorted(graph.boundary), "areas_mm2": graph.areas_mm2,
            "area_method": "integer_midpoint_cube_sphere_jacobian_dual_cells"}
        root_anchor = next(a for a in request.anchors if a.role == "outlet")
        root = graph.lookup[SurfacePoint(*root_anchor.point)]
        _, parent, rank, complete = flood(graph, [root], request.expansion_budget, radius)
        expansions = len(rank)
        used = set()
        for anchor in sorted(request.anchors, key=lambda a: a.id):
            if anchor.role == "outlet":
                continue
            start = graph.lookup[SurfacePoint(*anchor.point)]
            path = path_to(start, root, parent, rank)
            route = {"id": f"g1-route:{rid}:{anchor.id}", "source_anchor_id": anchor.id,
                "outlet_anchor_id": root_anchor.id, "source_role": anchor.role, "status": "pending_budget",
                "path_vertices": path or [], "segment_ids": [], "new_spring": False,
                "actual_flow_liters": None, "capacity_validation": "sampled_sections_only_not_hydraulic_capacity"}
            if path is not None:
                zs, longest = [], 0
                for a, b in zip(path, path[1:]):
                    used.add((a, b))
                    probes, profile = directed(graph, a, b)
                    zs.extend(profile[:-1])
                    longest = max(longest, *(probe_arc_upper_mm(u, v, radius) for u, v in zip(probes, probes[1:])))
                    route["segment_ids"].append(f"g1-segment:{plan.signature}:{checksum([list(graph.points[a].xyz), list(graph.points[b].xyz)])[:24]}")
                zs.append(graph.heights[root])
                head = zs[-1]
                envelope = [0]*len(zs)
                for i in range(len(zs)-1, -1, -1):
                    head = max(head, zs[i])
                    envelope[i] = head
                uphill = max([max(0, b-a) for a, b in zip(zs, zs[1:])] or [0])
                head_violations = []
                for endpoint in (anchor, root_anchor):
                    z = context.height(SurfacePoint(*endpoint.point))
                    if endpoint.reference_head_mm is not None and z > endpoint.reference_head_mm:
                        head_violations.append({"anchor_id": endpoint.id, "terrain_height_mm": z,
                            "fixed_reference_head_mm": endpoint.reference_head_mm, "excess_mm": z-endpoint.reference_head_mm,
                            "proof_scope": "fixed_endpoint_incompatible_not_all_possible_planetary_routes"})
                route.update({"terrain_profile_mm": zs, "minimum_static_envelope_mm": envelope,
                    "storage_raise_mm": [h-z for h, z in zip(envelope, zs)], "sampled_uphill_mm": uphill,
                    "max_probe_spacing_mm": longest, "endpoint_head_violations": head_violations,
                    "length_mm": sum(distance_mm(graph.points[a], graph.points[b], radius) for a, b in zip(path, path[1:])),
                    "geometric_condition": "sampled_descending" if not uphill else "storage_geometry_required",
                    "path_excess_above_source_reference_mm": max(0, max(zs)-anchor.reference_head_mm)
                        if anchor.reference_head_mm is not None else None,
                    "status": "incompatible_fixed_boundary_head" if head_violations else
                        "incompatible_sampled_path_reference_head" if anchor.reference_head_mm is not None and max(zs) > anchor.reference_head_mm else
                        "coincident_anchors_no_path_demonstrated" if len(path) < 2 else
                        "pending_resolution" if longest > request.target_spacing_m*1000 else
                        "partially_verified_storage_required" if uphill else "verified_at_requested_resolution"})
            result["routes"].append(route)
        for a, b in sorted(used):
            points, zs = directed(graph, a, b)
            length = distance_mm(graph.points[a], graph.points[b], radius)
            result["segments"].append({"id": f"g1-segment:{plan.signature}:{checksum([list(graph.points[a].xyz), list(graph.points[b].xyz)])[:24]}",
                "source_vertex": a, "target_vertex": b, "points": [list(p.xyz) for p in points],
                "terrain_profile_mm": list(zs), "length_mm": length,
                "longitudinal_drop_mm": zs[0]-zs[-1],
                "slope_rational": [zs[0]-zs[-1], length] if length else None,
                "sampled_uphill_mm": max([max(0, v-u) for u, v in zip(zs, zs[1:])] or [0]),
                "river_bed_excavated": False, "flow_active": False})
        incoming = {}
        for a, b in used:
            incoming.setdefault(b, set()).add(a)
        result["confluences"] = [{"vertex": b, "point": list(graph.points[b].xyz), "incoming_vertices": sorted(values),
            "outgoing_vertex": parent.get(b), "water_source": False} for b, values in sorted(incoming.items()) if len(values) > 1]
        result["status"] = "sampled_geometry_prepared" if complete else "partially_prepared_budget"
        result["coast"] = coastal_evidence(sampler, graph)
        result["depression_geometry"] = investigate(graph, radius, request.expansion_budget, rid)
        for route in result["routes"]:
            if "storage_raise_mm" not in route:
                continue
            raised = [v for i, v in enumerate(route["path_vertices"]) if route["storage_raise_mm"][4*i] > 0]
            basins = [b for b in result["depression_geometry"]["depressions"] if set(b["vertices"]) & set(raised)]
            covered = {v for b in basins for v in b["vertices"]}
            route["storage_evidence"] = {"sampled_basin_fragment_ids": [b["id"] for b in basins],
                "unresolved_raised_vertices": [v for v in raised if v not in covered],
                "subedge_storage_unresolved": any(v > 0 for i, v in enumerate(route["storage_raise_mm"]) if i%4),
                "water_occupation_and_throughflow_not_proved": True}
        candidates = sorted(used)
        if candidates and config.max_sections:
            chosen = sorted({candidates[i*len(candidates)//min(config.max_sections, len(candidates))]
                             for i in range(min(config.max_sections, len(candidates)))})
            for a, b in chosen:
                section = sample_section(context, graph.points[a], graph.points[b], radius, config)
                if section:
                    result["sections"].append({"vertex": a, **section})
    except BudgetExhausted as exc:
        result["issues"].append({"reason": str(exc), "meaning": "insufficient_budget_not_physical_blockage"})
        result["status"] = "partially_prepared_budget" if result["segments"] else "pending_budget"
    except ResolutionRequired as exc:
        result["issues"].append({"reason": str(exc), "meaning": "insufficient_resolution_not_physical_impossibility"})
        result["status"] = "pending_resolution"
    result["budget"] = {"sample_count": len(context.samples)+upstream_samples, "sample_limit": request.sample_budget,
        "upstream_port_search_samples": upstream_samples,
        "route_expansions": expansions, "expansion_limit": request.expansion_budget,
        "edge_probe_intervals": 4, "section_limit": config.max_sections}
    result["potential_overflow_locations"] = [
        {"kind": "sampled_depression_spill", "depression_id": b["id"], "height_mm": b["spill_height_mm"], "edges": b["spill_edges"]}
        for b in result["depression_geometry"]["depressions"]]
    result["potential_overflow_locations"] += [{"kind": "sampled_section_lateral_escape", "point": s["point"],
        "height_mm": s["sampled_lateral_escape_height_mm"]} for s in result["sections"] if s["sampled_lateral_escape_height_mm"] is not None]
    result["terrain_coverage"] = coverage_boxes(list(context.samples)+[tile.point(x, y, 1) for x in (0, 1) for y in (0, 1)])
    if len(json.dumps(result, separators=(",", ":")).encode()) > config.max_payload_bytes:
        # Keep an explicit immutable refusal, not an oversized or truncated proof.
        result.update({"status": "pending_persistence_budget", "graph": None, "routes": [], "segments": [],
            "sections": [], "confluences": [], "coast": None,
            "potential_overflow_locations": [],
            "depression_geometry": {"status": "not_retained_due_to_budget", "depressions": []}})
        result["issues"].append({"reason": "serialized_evidence_budget", "meaning": "split_or_refine_with_explicit_new_request"})
    if len(json.dumps(result, separators=(",", ":")).encode()) > config.max_payload_bytes:
        raise ValueError("G1 persistence budget cannot hold the canonical request metadata")
    validate_geometry(plan, request, result)
    return result


def validate_geometry(plan, request, data):
    if (data.get("kind") != "hydro_geometry_evidence_g1" or type(data.get("geometry_version")) is not int or
            data["geometry_version"] != 1 or data.get("signature") != plan.signature or
            data.get("terrain_signature") != plan.terrain.signature or data.get("hydrology_signature") != plan.hydrology.signature or
            data.get("hydrology_checksum") != plan.hydrology_checksum or data.get("hr_signature") != plan.hr_signature or
            data.get("request") != request.canonical() or
            data.get("request_id") != request_id(plan, request) or data.get("terrain_modified") is not False or
            data.get("water_ledger_modified") is not False or data.get("active_watercourses") != []):
        raise ValueError("G1 persisted evidence version/source/request mismatch")
    budget = data["budget"]
    if not 0 <= budget["sample_count"] <= request.sample_budget or not 0 <= budget["route_expansions"] <= request.expansion_budget:
        raise ValueError("Invalid G1 persisted budget")
    if len(json.dumps(data, separators=(",", ":")).encode()) > plan.config.max_payload_bytes:
        raise ValueError("G1 persisted evidence exceeds its size budget")
    graph = data.get("graph")
    edges = {}
    if graph is not None:
        points, heights, areas = graph["points"], graph["heights_mm"], graph["areas_mm2"]
        n, tile = request.grid_intervals, TerrainTile(*request.tile)
        if not (n+1)**2 <= len(points) <= (n+1)**2+len(request.anchors) or len(points) != len(heights) or len(points) != len(areas):
            raise ValueError("Invalid G1 graph dimensions")
        if any(type(z) is not int for z in heights) or any(type(a) is not int or a < 0 for a in areas):
            raise ValueError("Invalid G1 graph units")
        expected = [list(tile.point(x, y, n).xyz) for y in range(n+1) for x in range(n+1)]
        if points[:(n+1)**2] != expected:
            raise ValueError("G1 graph does not match its canonical tile")
        for point in points:
            if list(SurfacePoint(*point).xyz) != point:
                raise ValueError("Noncanonical G1 graph ray")
        for a, b, peak in graph["edges"]:
            if (any(type(v) is not int for v in (a, b, peak)) or not 0 <= a < b < len(points) or
                    (a, b) in edges or peak < max(heights[a], heights[b])):
                raise ValueError("Invalid G1 graph edge/peak")
            edges[a, b] = peak
    receivers, segments = {}, {}
    for segment in data["segments"]:
        a, b = segment["source_vertex"], segment["target_vertex"]
        if a == b or a in receivers and receivers[a] != b or segment["id"] in segments:
            raise ValueError("G1 divergent receiver or duplicate segment")
        receivers[a], segments[segment["id"]] = b, segment
        zs = segment["terrain_profile_mm"]
        if len(zs) != 5 or any(type(z) is not int for z in zs) or len(segment["points"]) != 5:
            raise ValueError("Invalid G1 terrain profile")
        if graph is None or tuple(sorted((a, b))) not in edges:
            raise ValueError("G1 segment is not part of its terrain graph")
        if (segment["points"][0] != points[a] or segment["points"][-1] != points[b] or
                zs[0] != heights[a] or zs[-1] != heights[b] or max(zs) != edges[tuple(sorted((a, b)))]):
            raise ValueError("G1 segment endpoint/profile mismatch")
        if segment["river_bed_excavated"] is not False or segment["flow_active"] is not False:
            raise ValueError("G1 cannot authorize terrain incision or water occupation")
    completed = set()
    for start in receivers:
        seen, node = set(), start
        while node in receivers and node not in completed:
            if node in seen:
                raise ValueError("G1 cycle")
            seen.add(node)
            node = receivers[node]
        completed.update(seen)
    for route in data["routes"]:
        if any(s not in segments for s in route["segment_ids"]):
            raise ValueError("Missing G1 route segment")
        if "terrain_profile_mm" in route:
            zs, hs = route["terrain_profile_mm"], route["minimum_static_envelope_mm"]
            if len(zs) != len(hs) or any(h < z for z, h in zip(zs, hs)) or any(a < b for a, b in zip(hs, hs[1:])):
                raise ValueError("G1 unexplained uphill/static storage")
            if route["storage_raise_mm"] != [h-z for h, z in zip(hs, zs)]:
                raise ValueError("G1 storage evidence mismatch")
            chosen = [segments[s] for s in route["segment_ids"]]
            if any(a["target_vertex"] != b["source_vertex"] for a, b in zip(chosen, chosen[1:])):
                raise ValueError("G1 disconnected route")
            anchors = {a.id: a for a in request.anchors}
            start, outlet = anchors[route["source_anchor_id"]], anchors[route["outlet_anchor_id"]]
            if chosen:
                rebuilt = [z for s in chosen for z in s["terrain_profile_mm"][:-1]]+[chosen[-1]["terrain_profile_mm"][-1]]
                if rebuilt != zs or chosen[0]["points"][0] != start.point or chosen[-1]["points"][-1] != outlet.point:
                    raise ValueError("G1 route does not join its prescribed anchors")
            if route["status"] == "verified_at_requested_resolution":
                if (not chosen or any(b > a for a, b in zip(zs, zs[1:])) or route["endpoint_head_violations"] or
                        route["max_probe_spacing_mm"] > request.target_spacing_m*1000 or
                        start.reference_head_mm is not None and max(zs) > start.reference_head_mm):
                    raise ValueError("G1 route claims unsupported verification")
    for basin in data["depression_geometry"]["depressions"]:
        curve = basin["potential_hypsometry"]
        if (basin["water_volume_liters"] is not None or basin["permanent"] is not None or
                any(c["potential_storage_liters"] < 0 for c in curve) or
                any(a["stage_mm"] >= b["stage_mm"] or a["potential_storage_liters"] > b["potential_storage_liters"]
                    for a, b in zip(curve, curve[1:]))):
            raise ValueError("Invalid G1 geometric capacity or occupancy")
