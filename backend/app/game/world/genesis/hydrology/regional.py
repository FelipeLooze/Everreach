"""HR1 subordinate regional potential: shared ports, confluence tree and refusals."""
from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

from ..formation_config import calibrated_scale
from ..formation_plan import indexed_cell
from ..sphere_topology import CellKey, SurfacePoint
from .geometry import geometry
from .regional_graph import MAX_GRAPHS, MAX_SAMPLES, SampleContext, directed_profile, flood, path_to
from .sectors import clip_segment, query_point


class RegionalHydrologyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    refinement_version: Literal[1] = 1
    hydrology_version: Literal[1] = 1
    depth: int = Field(default=3, ge=2, le=4)

    @field_validator("refinement_version", "hydrology_version", mode="before")
    @classmethod
    def integer_versions(cls, value):
        if type(value) is not int:
            raise ValueError("HR1 versions must be explicit integers")
        return value


def regional_signature(plan, config):
    return sha256(json.dumps(["hydrology-regional-hr1", plan.signature, config.model_dump()],
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def _identifier(signature, kind, value):
    return f"hydro-hr1:{signature}:{kind}:{value}"


def shared_port(plan, source: int, context: SampleContext, signature: str):
    """Bilateral contract, computed identically before either region is persisted."""
    if source not in plan.channel_index:
        raise ValueError("Only an existing H1 potential edge may be refined")
    target = plan.drainage.parent[source]
    a = context.graph(indexed_cell(source, plan.config.level))
    b = context.graph(indexed_cell(target, plan.config.level))
    candidates = sorted({a.points[i] for i in a.boundary} & {b.points[i] for i in b.boundary}, key=lambda p: p.xyz)
    if not candidates:
        raise ValueError("Incident macro cells have no shared regional samples")
    ca, _, _ = flood(a, a.center, a.heights[a.center])
    cb, _, _ = flood(b, b.center, plan.drainage.head[target])
    n = 2**context.depth
    def score(point):
        ia, ib = a.lookup[point], b.lookup[point]
        x, y = a.coordinates[ia]
        return max(ca[ia][0], cb[ib][0]), abs(x-n//2)+abs(y-n//2), point.xyz
    chosen = min(candidates, key=score)
    required = score(chosen)[0]
    edge = geometry(plan.config.level).edge_lookup[tuple(sorted((source, target)))]
    return {"id": _identifier(signature, "port", edge), "macro_edge_id": plan.identifier("edge", edge),
        "reach_id": plan.identifier("reach", plan.reaches[plan.channel_index[source]].start),
        "source_node": source, "target_node": target, "point": list(chosen.xyz),
        "h1_representative_port": list(geometry(plan.config.level).ports[edge].xyz),
        "potential_head_m": cb[b.lookup[chosen]][0], "terrain_m": context.height(chosen),
        "h1_source_head_m": plan.drainage.head[source], "h1_target_head_m": plan.drainage.head[target],
        "minimum_required_head_m": required, "candidate_count": len(candidates),
        "status": "sampled_pair_compatible" if required <= plan.drainage.head[source] else "incompatible_h1_head",
        "water_availability": "unknown", "discharge_m3_s": None, "perennial": None}


def build_regional_hydrology(source, plan, node: int, config=None, *, _sampler=None):
    config = config or RegionalHydrologyConfig()
    if (source.config.generator_version != 4 or source.signature != plan.source_signature
            or source.config.radius_m != plan.radius_m):
        raise ValueError("HR1 requires the pinned V4/H1 source")
    if type(node) is not int or not 0 <= node < len(plan.heights):
        raise ValueError("Invalid H1 region address")
    signature = regional_signature(plan, config)
    g, d = geometry(plan.config.level), plan.drainage
    incident = sorted({other for other, _ in g.adjacency[node]
        if other in plan.channel_index and d.parent[other] == node} | ({node} if node in plan.channel_index else set()))
    context = SampleContext(source, config.depth, _sampler)
    contracts = [shared_port(plan, i, context, signature) for i in incident]
    key = indexed_cell(node, plan.config.level)
    region = {"kind": "regional_hydrology_hr1", "refinement_version": 1, "signature": signature,
        "source_signature": source.signature, "hydrology_signature": plan.signature, "config": config.model_dump(),
        "node": node, "tile": [key.face, key.level, key.x, key.y], "ports": contracts,
        "h1_context": query_point(plan, g.points[node]),
        "h1_storage_candidate_id": plan.identifier("lake-candidate", d.depressions[plan.pool_index[node]][0])
            if node in plan.pool_index else None,
        "junction": {"id": plan.identifier("junction", node), "point": list(g.points[node].xyz),
            "potential_head_m": d.head[node], "terrain_m": plan.heights[node],
            "role": "macro_transfer_or_terminal_not_a_new_spring"},
        "routes": [], "segments": [], "issues": [], "depression_candidates": [],
        "water_balance": {"status": "not_modeled", "precipitation": None, "evaporation": None,
            "available_volume_m3": None, "seasonality": None},
        "actually_fed_watercourses": [], "river_bed_geometry_final": False,
        "guarantee": "bounded_sampled_potential_with_peer_and_subgrid_validation_pending",
        "terrain_detail_wavelength_m": calibrated_scale(source.config)["detail_wavelength_m"]}
    if incident:
        graph = context.graph(key)
        outgoing = next((p for p in contracts if p["source_node"] == node), None)
        receiver, heads, membership = {}, {graph.center: d.head[node]}, {}
        outgoing_path = [graph.center]
        if outgoing and outgoing["status"] == "sampled_pair_compatible":
            endpoint = graph.lookup[SurfacePoint(*outgoing["point"])]
            costs, parent, _ = flood(graph, endpoint, outgoing["potential_head_m"])
            outgoing_path = path_to(graph.center, endpoint, parent)
            height = outgoing["potential_head_m"]
            heads[endpoint] = height
            for a, b in reversed(list(zip(outgoing_path, outgoing_path[1:]))):
                height = max(height, max(directed_profile(graph, a, b)))
                heads[a] = height
                receiver[a] = b
            heads[graph.center] = d.head[node]
        blocked_outlet = outgoing is not None and outgoing["status"] != "sampled_pair_compatible"
        costs, parents, _ = flood(graph, graph.center, d.head[node], frozenset(outgoing_path[1:]))
        for port in contracts:
            ingress = port["target_node"] == node
            endpoint = graph.lookup[SurfacePoint(*port["point"])]
            route = {"macro_edge_id": port["macro_edge_id"], "reach_id": port["reach_id"],
                "port_id": port["id"], "role": "ingress" if ingress else "egress",
                "status": "sampled_compatible_peer_validation_pending", "segment_ids": []}
            if port["status"] != "sampled_pair_compatible":
                route["status"] = "incompatible_h1_head"
            elif blocked_outlet:
                route["status"] = "downstream_outlet_incompatible"
            elif ingress and (endpoint not in costs or costs[endpoint][0] > port["potential_head_m"]):
                route["status"] = "local_confluence_conflict"
            if route["status"] != "sampled_compatible_peer_validation_pending":
                region["issues"].append({"macro_edge_id": port["macro_edge_id"], "reason": route["status"],
                    "minimum_pair_head_m": port["minimum_required_head_m"],
                    "required_local_head_m": costs.get(endpoint, (None,))[0] if ingress else None,
                    "action": "needs_bounded_larger_or_finer_refinement_no_terrain_change"})
                region["routes"].append(route)
                continue
            path = path_to(endpoint, graph.center, parents) if ingress else outgoing_path
            if ingress:
                for a, b in zip(path, path[1:]):
                    receiver[a] = b
                    heads[a] = costs[a][0]
                heads[endpoint] = port["potential_head_m"]
            route["_path"] = path
            for a, b in zip(path, path[1:]):
                membership.setdefault((a, b), set()).add(port["macro_edge_id"])
            region["routes"].append(route)
        segment_ids = {}
        for (a, b), edges in sorted(membership.items()):
            identifier = _identifier(signature, "segment", f"{node}.{a}.{b}")
            segment_ids[a, b] = identifier
            raw = directed_profile(graph, a, b)
            envelope, height = [0]*5, heads[b]
            for i in range(4, -1, -1):
                height = max(height, raw[i])
                envelope[i] = height
            if envelope[0] > heads[a]:
                raise ValueError("Regional route exceeds its fixed upstream head")
            envelope[0] = heads[a]
            region["segments"].append({"id": identifier, "source_vertex": a, "target_vertex": b,
                "points": [list(graph.points[a].xyz), list(graph.points[b].xyz)],
                "terrain_profile_m": list(raw), "potential_head_profile_m": envelope,
                "storage_raise_m": [h-z for h, z in zip(envelope, raw)],
                "upstream_macro_edge_ids": sorted(edges), "actual_wet_state": None})
        for route in region["routes"]:
            path = route.pop("_path", [])
            route["segment_ids"] = [segment_ids[a, b] for a, b in zip(path, path[1:])]
        for i in range(len(graph.points)):
            if i in graph.boundary:
                continue
            if all((graph.heights[j], j) >= (graph.heights[i], i) or
                   max(graph.profiles[tuple(sorted((i, j)))]) > graph.heights[i] for j in graph.adjacent[i]):
                region["depression_candidates"].append({"id": _identifier(signature, "depression", f"{node}.{i}"),
                    "point": list(graph.points[i].xyz), "bottom_sample_m": graph.heights[i],
                    "extent": "unresolved_open_patch_candidate", "permanent": None, "volume_available_m3": None})
    region["budget"] = {"sample_count": len(context.samples), "sample_limit": MAX_SAMPLES,
        "graph_count": len(context.graphs), "graph_limit": MAX_GRAPHS,
        "vertices_per_graph_limit": (2**config.depth+1)**2-4}
    validate_region(region)
    return region


def validate_region(region):
    if (region.get("kind") != "regional_hydrology_hr1" or type(region.get("refinement_version")) is not int
            or region.get("refinement_version") != 1):
        raise ValueError("Unsupported regional hydrology version")
    config = RegionalHydrologyConfig.model_validate(region["config"])
    tile = CellKey(*region["tile"])
    from ..formation_plan import cell_index
    if tile.level not in range(2, 6) or cell_index(tile) != region["node"]:
        raise ValueError("Regional address mismatch")
    budget = region["budget"]
    if (not 0 <= budget["sample_count"] <= MAX_SAMPLES or not 0 <= budget["graph_count"] <= MAX_GRAPHS
            or budget["vertices_per_graph_limit"] != (2**config.depth+1)**2-4):
        raise ValueError("Invalid regional budget")
    ports = {p["id"]: p for p in region["ports"]}
    if len(ports) != len(region["ports"]) or len(ports) > 4:
        raise ValueError("Duplicate or excess ports")
    for port in ports.values():
        SurfacePoint(*port["point"])
        if port["status"] == "sampled_pair_compatible" and not (
                port["terrain_m"] <= port["potential_head_m"] <= port["h1_source_head_m"]
                and port["h1_target_head_m"] <= port["potential_head_m"]
                and port["minimum_required_head_m"] <= port["h1_source_head_m"]):
            raise ValueError("Port violates H1 head bounds")
    segments, receiver, vertex_heads = {}, {}, {}
    for segment in region["segments"]:
        sid, a, b = segment["id"], segment["source_vertex"], segment["target_vertex"]
        if sid in segments or a in receiver or a == b:
            raise ValueError("Duplicate segment, divergent receiver or self cycle")
        segments[sid], receiver[a] = segment, b
        heads, raw = segment["potential_head_profile_m"], segment["terrain_profile_m"]
        if (len(heads) != 5 or len(raw) != 5 or any(type(z) is not int for z in heads+raw)
                or any(x < y for x, y in zip(heads, heads[1:]))
                or any(h < z for h, z in zip(heads, raw))
                or segment["storage_raise_m"] != [h-z for h, z in zip(heads, raw)]):
            raise ValueError("Unexplained regional uphill flow/storage")
        for vertex, head, point in ((a, heads[0], segment["points"][0]), (b, heads[-1], segment["points"][-1])):
            identity = head, SurfacePoint(*point)
            if vertex in vertex_heads and vertex_heads[vertex] != identity:
                raise ValueError("Inconsistent confluence head or point")
            vertex_heads[vertex] = identity
    visited = set()
    for start in receiver:
        path, node = set(), start
        while node in receiver and node not in visited:
            if node in path:
                raise ValueError("Cyclic regional flow")
            path.add(node)
            node = receiver[node]
        visited.update(path)
    used = set()
    for route in region["routes"]:
        port = ports[route["port_id"]]
        ids = route["segment_ids"]
        if route["status"] != "sampled_compatible_peer_validation_pending":
            if ids:
                raise ValueError("Incompatible route must not fabricate a path")
            continue
        if not ids or port["status"] != "sampled_pair_compatible":
            raise ValueError("Compatible route missing samples/port")
        path = [segments[sid] for sid in ids]
        if any(a["target_vertex"] != b["source_vertex"] for a, b in zip(path, path[1:])):
            raise ValueError("Disconnected route")
        start, end = (port, region["junction"]) if route["role"] == "ingress" else (region["junction"], port)
        if (path[0]["points"][0] != start["point"] or path[-1]["points"][-1] != end["point"]
                or path[0]["potential_head_profile_m"][0] != start["potential_head_m"]
                or path[-1]["potential_head_profile_m"][-1] != end["potential_head_m"]):
            raise ValueError("Route does not satisfy its boundary conditions")
        used.update(ids)
    if used != set(segments):
        raise ValueError("Orphan regional segments")


def regional_sector_snapshot(region: dict, key: CellKey):
    tile = CellKey(*region["tile"])
    if key.level < tile.level or key.parent(tile.level) != tile:
        raise ValueError("Query must be inside the persisted canonical HR1 region")
    pieces = []
    for segment in region["segments"]:
        result = clip_segment(*(SurfacePoint(*p) for p in segment["points"]), key)
        if result:
            points = [list(p.xyz) for p in result]
            def identifier(point):
                for port in region["ports"]:
                    if list(point.xyz) == port["point"]:
                        return port["id"]
                if list(point.xyz) == region["junction"]["point"]:
                    return region["junction"]["id"]
                value = list(point.xyz) if list(point.xyz) in segment["points"] else [segment["id"], list(point.xyz)]
                digest = sha256(json.dumps(value).encode()).hexdigest()[:24]
                return _identifier(region["signature"], "sector-port", digest)
            def condition(point):
                for index, endpoint in enumerate(segment["points"]):
                    if list(point.xyz) == endpoint:
                        return {"kind": "exact_sampled_potential_head", "head_m":
                            segment["potential_head_profile_m"][0 if index == 0 else -1]}
                return {"kind": "sampled_head_bounds", "minimum_m": segment["potential_head_profile_m"][-1],
                        "maximum_m": segment["potential_head_profile_m"][0]}
            pieces.append({"segment_id": segment["id"], "points": points,
                "entry_port_id": identifier(result[0]), "exit_port_id": identifier(result[1]),
                "entry_head_condition": condition(result[0]), "exit_head_condition": condition(result[1]),
                "potential_head_bounds_m": [segment["potential_head_profile_m"][-1],
                                             segment["potential_head_profile_m"][0]],
                "actual_wet_state": None, "river_bed_geometry_final": False})
    return {"refinement_version": 1, "signature": region["signature"], "node": region["node"],
        "sector": [key.face, key.level, key.x, key.y], "pieces": pieces,
        "issues": region["issues"], "actually_fed_watercourses": [], "water_balance": "not_modeled"}


def compare_regional_connection(first, second, port_id):
    """A port alone is insufficient: both locally routed halves must be checked."""
    for region in (first, second):
        validate_region(region)
    if first["signature"] != second["signature"] or first["node"] == second["node"]:
        raise ValueError("Cannot connect different refinements or a region to itself")
    ports = [next((p for p in r["ports"] if p["id"] == port_id), None) for r in (first, second)]
    if ports[0] is None or ports[0] != ports[1]:
        raise ValueError("Missing or inconsistent bilateral contract")
    port = ports[0]
    if {first["node"], second["node"]} != {port["source_node"], port["target_node"]}:
        raise ValueError("Port is not incident to both regions")
    routes = [next(r for r in region["routes"] if r["port_id"] == port_id) for region in (first, second)]
    compatible = all(r["status"] == "sampled_compatible_peer_validation_pending" for r in routes)
    return {"port_id": port_id, "macro_edge_id": port["macro_edge_id"],
        "source_node": port["source_node"], "target_node": port["target_node"],
        "point": port["point"], "potential_head_m": port["potential_head_m"],
        "status": "connected_sampled_potential" if compatible else "refinement_incompatible",
        "local_statuses": [r["status"] for r in routes], "actual_wet_state": None,
        "subgrid_validation_pending": True}
