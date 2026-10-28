"""Exact angular area for radial cube charts; diagnostic floating point only.

Integrate (1+u²+v²)^(-3/2) on the face rectangle. Its corner primitive
is atan2(u*v, sqrt(1+u²+v²)). Physical area is solid angle * radius².
"""
from math import atan2, hypot, sqrt

from .sphere_topology import CellKey, cell_vertices


def rectangle_solid_angle(u0: float, v0: float, u1: float, v1: float) -> float:
    if not (-1 <= u0 < u1 <= 1 and -1 <= v0 < v1 <= 1):
        raise ValueError("Expected an ordered rectangle on a cube face")
    def primitive(u, v):
        return atan2(u*v, sqrt(1+u*u+v*v))
    return primitive(u1, v1)-primitive(u0, v1)-primitive(u1, v0)+primitive(u0, v0)


def cell_solid_angle(key: CellKey) -> float:
    if key.level >= 10:
        # Corner inclusion/exclusion loses relative precision on tiny cells.
        # Integer determinants avoid cancellation in the triangle numerator.
        a, b, c, d = cell_vertices(key)
        return _triangle_area(a.xyz, b.xyz, c.xyz)+_triangle_area(a.xyz, c.xyz, d.xyz)
    size = 2**key.level
    return rectangle_solid_angle(2*key.x/size-1, 2*key.y/size-1,
                                 2*(key.x+1)/size-1, 2*(key.y+1)/size-1)


def _triangle_area(a, b, c) -> float:
    cross = b[1]*c[2]-b[2]*c[1], b[2]*c[0]-b[0]*c[2], b[0]*c[1]-b[1]*c[0]
    dot = lambda x, y: sum(i*j for i, j in zip(x, y))
    na, nb, nc = hypot(*a), hypot(*b), hypot(*c)
    return 2*atan2(abs(dot(a, cross)), na*nb*nc+dot(a, b)*nc+dot(b, c)*na+dot(c, a)*nb)
