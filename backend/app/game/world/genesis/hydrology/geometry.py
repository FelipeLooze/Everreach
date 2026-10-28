"""Fixed integer cube-sphere graph and deterministic area quadrature."""
from dataclasses import dataclass
from functools import lru_cache
from math import isqrt
from types import MappingProxyType
from typing import Mapping

from ..coast_refinement import _between
from ..formation_plan import cell_index, indexed_cell
from ..sphere_topology import DIRECTIONS, SurfacePoint, cell_center, edge_points, neighbor

AREA_UNIT = 2**50


def angular_area_units(level: int, x: int, y: int) -> int:
    """4x4 midpoint quadrature; integer steradian units, not precipitation."""
    n = 4*2**level
    weight = 0
    for dy in range(4):
        for dx in range(4):
            u, v = 2*(4*x+dx)+1-n, 2*(4*y+dy)+1-n
            weight += isqrt(n**6*AREA_UNIT**2//(n*n+u*u+v*v)**3)
    return 4*weight//(n*n)


@dataclass(frozen=True)
class HydroGeometry:
    level: int
    points: tuple[SurfacePoint, ...]
    edges: tuple[tuple[int, int], ...]
    ports: tuple[SurfacePoint, ...]
    profiles: tuple[tuple[SurfacePoint, ...], ...]
    adjacency: tuple[tuple[tuple[int, int], ...], ...]  # (neighbor node, edge index)
    area_units: tuple[int, ...]
    edge_lookup: Mapping[tuple[int, int], int]


@lru_cache(maxsize=2)
def geometry(level: int) -> HydroGeometry:
    if type(level) is not int or not 2 <= level <= 5:
        raise ValueError("H1 level must be 2..5 (at most 6,144 nodes)")
    count = 6*4**level
    keys = tuple(indexed_cell(i, level) for i in range(count))
    points = tuple(cell_center(key) for key in keys)
    edges, ports, profiles, adjacency = [], [], [], [[] for _ in keys]
    lookup = {}
    for a, key in enumerate(keys):
        for direction in DIRECTIONS:
            b = cell_index(neighbor(key, direction))
            if a >= b:
                continue
            edge = len(edges)
            port = edge_points(key, direction, 2)[1]
            edges.append((a, b))
            ports.append(port)
            profiles.append((points[a], _between(points[a], port, 1, 2), port,
                             _between(port, points[b], 1, 2), points[b]))
            adjacency[a].append((b, edge))
            adjacency[b].append((a, edge))
            lookup[(a, b)] = edge
    return HydroGeometry(level, points, tuple(edges), tuple(ports), tuple(profiles),
        tuple(tuple(sorted(row)) for row in adjacency),
        tuple(angular_area_units(level, k.x, k.y) for k in keys), MappingProxyType(lookup))
