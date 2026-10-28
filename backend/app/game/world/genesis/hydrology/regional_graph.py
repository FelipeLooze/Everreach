"""Bounded V4 sample graphs; integer minimax paths, never terrain incision."""
from dataclasses import dataclass
from fractions import Fraction
from heapq import heappop, heappush

from ..formation_tectonics import evaluate
from ..sphere_topology import SurfacePoint
from .sectors import _face_uv, _ray

MAX_SAMPLES = 12_000
MAX_GRAPHS = 5


@dataclass
class RegionalGraph:
    key: object
    points: tuple
    coordinates: tuple
    heights: tuple
    profiles: dict
    adjacent: tuple
    center: int
    boundary: frozenset
    lookup: dict


def flood(graph: RegionalGraph, root: int, head: int, excluded=frozenset()):
    """Receiver points toward root; (minimax head, hops, index) breaks ties."""
    costs, parent, rank = {root: (head, 0)}, {}, {}
    pending = [(head, 0, root)]
    while pending:
        height, hops, node = heappop(pending)
        if node in rank or costs[node] != (height, hops):
            continue
        rank[node] = len(rank)
        for other in graph.adjacent[node]:
            if other in excluded or other in rank:
                continue
            candidate = max(height, max(graph.profiles[tuple(sorted((node, other)))])), hops+1
            if other not in costs or candidate < costs[other]:
                costs[other], parent[other] = candidate, node
                heappush(pending, (*candidate, other))
    return costs, parent, rank


def path_to(start: int, root: int, parent: dict):
    path = [start]
    while path[-1] != root:
        if path[-1] not in parent or len(path) > len(parent)+1:
            raise ValueError("Missing or cyclic regional receiver")
        path.append(parent[path[-1]])
    return path


class SampleContext:
    """One preparation request owns at most five graphs and 12,000 samples."""
    def __init__(self, source, depth: int, sampler=None):
        if type(depth) is not int or not 2 <= depth <= 4:
            raise ValueError("HR1 depth must be 2..4")
        self.source, self.depth = source, depth
        self.samples, self.graphs = {}, {}
        self.sampler = sampler or (lambda p: evaluate(source.seed, source.config, source.plates,
                                                     p, causes=False)["elevation_m"])

    def height(self, point):
        if point not in self.samples:
            if len(self.samples) >= MAX_SAMPLES:
                raise ValueError("HR1 sample budget exhausted")
            value = self.sampler(point)
            if type(value) is not int:
                raise ValueError("Regional terrain requires authoritative integer metres")
            self.samples[point] = value
        return self.samples[point]

    def graph(self, key):
        if key in self.graphs:
            return self.graphs[key]
        if len(self.graphs) >= MAX_GRAPHS:
            raise ValueError("HR1 graph budget exhausted")
        n, size = 2**self.depth, 2**key.level
        coordinates = tuple((x, y) for y in range(n+1) for x in range(n+1)
                            if 0 < x < n or 0 < y < n)
        def point(x, y):
            return _ray(key.face, Fraction(2*(key.x*n+x), size*n)-1,
                        Fraction(2*(key.y*n+y), size*n)-1)
        points = tuple(point(x, y) for x, y in coordinates)
        lookup = {p: i for i, p in enumerate(points)}
        grid = {xy: i for i, xy in enumerate(coordinates)}
        adjacent, profiles = [[] for _ in points], {}
        boundary = frozenset(i for i, (x, y) in enumerate(coordinates) if x in (0, n) or y in (0, n))
        heights = tuple(self.height(p) for p in points)
        for a, (x, y) in enumerate(coordinates):
            for xy in ((x+1, y), (x, y+1)):
                b = grid.get(xy)
                if b is None or (a in boundary and b in boundary):
                    continue
                profiles[a, b] = tuple(self.height(point(Fraction(x*(4-t)+xy[0]*t, 4),
                    Fraction(y*(4-t)+xy[1]*t, 4))) for t in range(5))
                adjacent[a].append(b)
                adjacent[b].append(a)
        graph = RegionalGraph(key, points, coordinates, heights, profiles,
            tuple(tuple(sorted(row)) for row in adjacent), grid[n//2, n//2], boundary, lookup)
        self.graphs[key] = graph
        return graph


def directed_profile(graph, a, b):
    values = graph.profiles[tuple(sorted((a, b)))]
    return values if a < b else values[::-1]
