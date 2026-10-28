"""Shared cube vertices give C0 bilinear fields across all face boundaries."""
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from math import isqrt

from ..sphere_topology import face_point, owning_face
from ..hydrology.sectors import _face_uv

Q = 1_000_000


def unit(point):
    norm = isqrt(sum(x*x for x in point.xyz)*Q*Q)
    return tuple(x*Q*Q//norm for x in point.xyz)


@dataclass(frozen=True)
class ClimateGeometry:
    level: int
    points: tuple
    directions: tuple
    faces: tuple
    adjacent: tuple


@lru_cache(maxsize=2)
def geometry(level):
    if type(level) is not int or not 3 <= level <= 5:
        raise ValueError("C1 level must be 3..5")
    n = 2**level
    charts = [tuple(face_point(f, x, y, n) for y in range(n+1) for x in range(n+1)) for f in range(6)]
    points = tuple(sorted(set(p for face in charts for p in face), key=lambda p: p.xyz))
    lookup = {p: i for i, p in enumerate(points)}
    faces = tuple(tuple(lookup[p] for p in face) for face in charts)
    adjacent = [set() for _ in points]
    for face in faces:
        for y in range(n+1):
            for x in range(n+1):
                a = face[y*(n+1)+x]
                for xx, yy in ((x+1, y), (x, y+1)):
                    if xx <= n and yy <= n:
                        b = face[yy*(n+1)+xx]
                        adjacent[a].add(b)
                        adjacent[b].add(a)
    return ClimateGeometry(level, points, tuple(unit(p) for p in points), faces,
                           tuple(tuple(sorted(row)) for row in adjacent))


def stencil(point, level, face=None):
    g, n = geometry(level), 2**level
    face = owning_face(point) if face is None else face
    u, v = _face_uv(point, face)
    x, y = (u+1)*n/2, (v+1)*n/2
    if not 0 <= x <= n or not 0 <= y <= n:
        raise ValueError("Point outside selected climate chart")
    ix, iy = min(n-1, x.numerator//x.denominator), min(n-1, y.numerator//y.denominator)
    fx, fy = x-ix, y-iy
    return tuple((g.faces[face][(iy+dy)*(n+1)+ix+dx], wx*wy)
                 for dx, wx in ((0, 1-fx), (1, fx)) for dy, wy in ((0, 1-fy), (1, fy)))


def interpolate(values, weights):
    value = sum((values[i]*w for i, w in weights), Fraction(0))
    return value.numerator//value.denominator
