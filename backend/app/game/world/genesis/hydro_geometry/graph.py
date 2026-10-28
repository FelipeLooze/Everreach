"""Bounded T1 graphs and deterministic minimax paths; never terrain incision."""
from dataclasses import dataclass
from heapq import heappop, heappush
from ..sphere_topology import SurfacePoint
from ..terrain.address import chart
from .spatial import between, distance_mm, vertex_areas_mm2


class BudgetExhausted(Exception):
    pass


class ResolutionRequired(Exception):
    pass


class SampleContext:
    def __init__(self, sampler, limit):
        self.sampler, self.limit = sampler, limit
        self.samples = {}
        self.profiles = {}

    def height(self, p):
        if p not in self.samples:
            if len(self.samples) >= self.limit:
                raise BudgetExhausted("T1 sample budget exhausted")
            z = self.sampler.sample(p)["height_mm"]
            if type(z) is not int:
                raise ValueError("G1 needs authoritative integer millimetres")
            self.samples[p] = z
        return self.samples[p]

    def profile(self, a, b):
        key = tuple(sorted((a.xyz, b.xyz)))
        if key not in self.profiles:
            pa, pb = (SurfacePoint(*v) for v in key)
            points = tuple(between(pa, pb, i) for i in range(5))
            self.profiles[key] = points, tuple(self.height(p) for p in points)
        points, heights = self.profiles[key]
        return (points, heights) if a.xyz <= b.xyz else (points[::-1], heights[::-1])


@dataclass
class Graph:
    tile: object
    points: list
    heights: list
    adjacent: list
    boundary: set
    lookup: dict
    profiles: dict
    areas_mm2: list


def build_graph(context, tile, n, anchors, radius):
    points = [tile.point(x, y, n) for y in range(n+1) for x in range(n+1)]
    lookup = {p: i for i, p in enumerate(points)}
    boundary = {y*(n+1)+x for y in range(n+1) for x in range(n+1) if x in (0, n) or y in (0, n)}
    edges = {tuple(sorted((y*(n+1)+x, y*(n+1)+x+1))) for y in range(n+1) for x in range(n)}
    edges |= {tuple(sorted((y*(n+1)+x, (y+1)*(n+1)+x))) for y in range(n) for x in range(n+1)}
    occupied = set()
    for anchor in sorted(anchors, key=lambda a: a.id):
        p = SurfacePoint(*anchor.point)
        if p in lookup:
            continue
        _, u, v, d = chart(p, tile.face)
        xu, yv = (u*2**tile.level-tile.x*d)*n, (v*2**tile.level-tile.y*d)*n
        x, y = min(n-1, xu//d), min(n-1, yv//d)
        cell = x, y
        if cell in occupied:
            raise ResolutionRequired("Multiple non-grid anchors in one cell; refine the requested tile")
        occupied.add(cell)
        index = len(points)
        lookup[p] = index
        points.append(p)
        if xu%d == 0:
            a, b = y*(n+1)+xu//d, (y+1)*(n+1)+xu//d
            edges.discard(tuple(sorted((a, b))))
            corners = (a, b)
        elif yv%d == 0:
            a, b = (yv//d)*(n+1)+x, (yv//d)*(n+1)+x+1
            edges.discard(tuple(sorted((a, b))))
            corners = (a, b)
        else:
            corners = (y*(n+1)+x, y*(n+1)+x+1, (y+1)*(n+1)+x, (y+1)*(n+1)+x+1)
        edges |= {tuple(sorted((index, a))) for a in corners}
        if xu in (0, n*d) or yv in (0, n*d):
            boundary.add(index)
    heights = [context.height(p) for p in points]
    profiles, adjacent = {}, [[] for _ in points]
    for a, b in sorted(edges):
        profiles[a, b] = context.profile(points[a], points[b])
        adjacent[a].append(b)
        adjacent[b].append(a)
    areas = vertex_areas_mm2(tile, n, radius)+[0]*(len(points)-(n+1)**2)
    return Graph(tile, points, heights, [tuple(sorted(a)) for a in adjacent], boundary, lookup, profiles, areas)


def directed(graph, a, b):
    points, heights = graph.profiles[tuple(sorted((a, b)))]
    return (points, heights) if a < b else (points[::-1], heights[::-1])


def flood(graph, roots, budget, radius):
    costs, parent, rank, pending = {}, {}, {}, []
    for root in sorted(roots):
        costs[root] = graph.heights[root], 0, 0
        heappush(pending, (*costs[root], root))
    while pending:
        head, rise, length, node = heappop(pending)
        if node in rank or costs[node] != (head, rise, length):
            continue
        if len(rank) >= budget:
            return costs, parent, rank, False
        rank[node] = len(rank)
        for other in graph.adjacent[node]:
            if other in rank:
                continue
            _, zs = directed(graph, other, node)
            candidate = (max(head, max(zs)), rise+sum(max(0, b-a) for a, b in zip(zs, zs[1:])),
                         length+distance_mm(graph.points[node], graph.points[other], radius))
            if other not in costs or candidate < costs[other]:
                costs[other], parent[other] = candidate, node
                heappush(pending, (*candidate, other))
    return costs, parent, rank, True


def path_to(start, root, parent, rank):
    if start not in rank:
        return None
    path = [start]
    while path[-1] != root:
        if path[-1] not in parent or len(path) > len(rank):
            raise ValueError("Invalid G1 receiver tree")
        path.append(parent[path[-1]])
    return path
