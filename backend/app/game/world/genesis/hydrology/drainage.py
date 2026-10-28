"""Deterministic graph conditioning and drainage, without changing terrain."""
from dataclasses import dataclass
from heapq import heappop, heappush


@dataclass(frozen=True)
class Drainage:
    marine: tuple[bool, ...]
    water_components: tuple[tuple[int, ...], ...]
    parent: tuple[int, ...]
    raw_parent: tuple[int, ...]
    head: tuple[int, ...]
    rank: tuple[int, ...]
    area: tuple[int, ...]
    order: tuple[int, ...]
    outlet: tuple[int, ...]
    raw_outlet: tuple[int, ...]
    raw_area: tuple[int, ...]
    depressions: tuple[tuple[int, ...], ...]


def solve(heights: tuple[int, ...], edges: tuple[tuple[int, int], ...], sills: tuple[int, ...],
          cell_area: tuple[int, ...], sea_level: int) -> Drainage:
    count = len(heights)
    if not count or len(cell_area) != count or len(edges) != len(sills):
        raise ValueError("Inconsistent drainage input")
    adjacent = [[] for _ in heights]
    for index, ((a, b), sill) in enumerate(zip(edges, sills)):
        if not 0 <= a < b < count or sill < max(heights[a], heights[b]):
            raise ValueError("Invalid graph edge or terrain sill")
        adjacent[a].append((b, index))
        adjacent[b].append((a, index))
    adjacent = [sorted(row) for row in adjacent]
    visited, water = set(), []
    for start in range(count):
        if start in visited or heights[start] >= sea_level:
            continue
        pending, members = [start], []
        visited.add(start)
        while pending:
            node = pending.pop()
            members.append(node)
            for other, edge in adjacent[node]:
                if other not in visited and heights[other] < sea_level and sills[edge] < sea_level:
                    visited.add(other)
                    pending.append(other)
        water.append(tuple(sorted(members)))
    reference = max(water, key=lambda group: (sum(cell_area[i] for i in group), -group[0]), default=())
    reference_set = set(reference)
    marine = tuple(i in reference_set for i in range(count))
    roots = reference or (min(range(count), key=lambda i: (heights[i], i)),)
    parent, heads, rank, queue = [-1]*count, [None]*count, [-1]*count, []
    for root in roots:
        heads[root] = sea_level if reference else heights[root]
        heappush(queue, (heads[root], root))
    settled = []
    while queue:
        head, node = heappop(queue)
        if rank[node] >= 0 or heads[node] != head:
            continue
        rank[node] = len(settled)
        settled.append(node)
        for other, edge in adjacent[node]:
            if rank[other] >= 0:
                continue
            candidate = max(heights[other], head, sills[edge])
            if heads[other] is None or candidate < heads[other]:
                heads[other], parent[other] = candidate, node
                heappush(queue, (candidate, other))
    if len(settled) != count:
        raise ValueError("Hydrological graph must cover a connected surface")
    raw_head = [sea_level if marine[i] else heights[i] for i in range(count)]
    raw_parent = [-1]*count
    for node in range(count):
        if marine[node]:
            continue
        candidates = [other for other, edge in adjacent[node]
            if sills[edge] <= raw_head[node] and (raw_head[other], other) < (raw_head[node], node)]
        if candidates:
            raw_parent[node] = min(candidates, key=lambda i: (raw_head[i], i))
    raw_outlet = list(range(count))
    for node in sorted(range(count), key=lambda i: (raw_head[i], i)):
        if raw_parent[node] >= 0:
            raw_outlet[node] = raw_outlet[raw_parent[node]]
    area = [0 if marine[i] else cell_area[i] for i in range(count)]
    raw_area = area.copy()
    for node in sorted(range(count), key=lambda i: (raw_head[i], i), reverse=True):
        if raw_parent[node] >= 0:
            raw_area[raw_parent[node]] += raw_area[node]
    order, child_max, child_matches, outlet = [1]*count, [0]*count, [0]*count, list(range(count))
    for node in settled:
        if parent[node] >= 0:
            outlet[node] = outlet[parent[node]]
    for node in reversed(settled):
        order[node] = child_max[node]+(child_matches[node] >= 2) if child_max[node] else 1
        p = parent[node]
        if p >= 0:
            area[p] += area[node]
            if order[node] > child_max[p]:
                child_max[p], child_matches[p] = order[node], 1
            elif order[node] == child_max[p]:
                child_matches[p] += 1
    pools, seen = [], set()
    for start in range(count):
        if marine[start] or heads[start] <= heights[start] or start in seen:
            continue
        pending, members = [start], []
        seen.add(start)
        while pending:
            node = pending.pop()
            members.append(node)
            for other, edge in adjacent[node]:
                if (other not in seen and not marine[other] and heights[other] < heads[other] == heads[start]
                        and sills[edge] <= heads[start]):
                    seen.add(other)
                    pending.append(other)
        pools.append(tuple(sorted(members)))
    result = Drainage(marine, tuple(water), tuple(parent), tuple(raw_parent), tuple(heads), tuple(rank),
        tuple(area), tuple(order), tuple(outlet), tuple(raw_outlet), tuple(raw_area), tuple(pools))
    validate(result, heights, edges, sills, cell_area, sea_level)
    return result


def validate(result: Drainage, heights, edges, sills, cell_area, sea_level: int) -> None:
    count = len(heights)
    if any(len(getattr(result, name)) != count for name in ("marine", "parent", "raw_parent", "head", "rank", "area", "order", "outlet", "raw_outlet", "raw_area")):
        raise ValueError("Inconsistent drainage arrays")
    if sorted(result.rank) != list(range(count)):
        raise ValueError("Invalid hydrological rank")
    for name in ("parent", "raw_parent", "head", "rank", "area", "order", "outlet", "raw_outlet", "raw_area"):
        if any(type(value) is not int for value in getattr(result, name)):
            raise ValueError("Hydrology decisions require integer arrays")
    if any(type(value) is not bool for value in result.marine):
        raise ValueError("Invalid marine mask")
    edge_sill = {pair: sill for pair, sill in zip(edges, sills)}
    raw_head = [sea_level if result.marine[i] else heights[i] for i in range(count)]
    expected_area = [0 if result.marine[i] else cell_area[i] for i in range(count)]
    expected_raw = expected_area.copy()
    for i, p in enumerate(result.parent):
        if result.head[i] < heights[i] or result.area[i] < 0:
            raise ValueError("Conditioning below terrain or negative contribution")
        if p < -1:
            raise ValueError("Invalid terminal marker")
        if p < 0:
            if result.outlet[i] != i:
                raise ValueError("Invalid outlet")
            continue
        if not 0 <= p < count or result.rank[p] >= result.rank[i] or result.head[p] > result.head[i]:
            raise ValueError("Cyclic or uphill conditioned flow")
        if edge_sill.get(tuple(sorted((i, p))), result.head[i]+1) > result.head[i]:
            raise ValueError("Conditioned flow crosses an unexplained barrier")
        if result.outlet[i] != result.outlet[p]:
            raise ValueError("Outlet lineage mismatch")
        expected_area[p] += result.area[i]
    for i, p in enumerate(result.raw_parent):
        if p < -1 or p >= count:
            raise ValueError("Invalid unconditioned receiver")
        if p >= 0:
            if ((raw_head[p], p) >= (raw_head[i], i) or
                    edge_sill.get(tuple(sorted((i, p))), raw_head[i]+1) > raw_head[i] or
                    result.raw_outlet[i] != result.raw_outlet[p]):
                raise ValueError("Cyclic/uphill unconditioned flow or raw outlet mismatch")
            expected_raw[p] += result.raw_area[i]
        elif result.raw_outlet[i] != i:
            raise ValueError("Invalid raw terminal")
    if tuple(expected_area) != result.area or tuple(expected_raw) != result.raw_area:
        raise ValueError("Node contributing area is inconsistent")
    terminals = sum(result.area[i] for i, p in enumerate(result.parent) if p < 0)
    if terminals != sum(a for a, sea in zip(cell_area, result.marine) if not sea):
        raise ValueError("Contributing area is not conserved")
