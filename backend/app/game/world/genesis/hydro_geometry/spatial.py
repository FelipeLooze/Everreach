from math import isqrt
from ..sphere_topology import BASES, DIRECTIONS, SurfacePoint
from ..terrain.address import TerrainTile, chart

UNIT = 2**50


def direction(point):
    norm = isqrt(sum(v*v for v in point.xyz)*UNIT**2)
    return tuple(v*UNIT**2//norm for v in point.xyz)


def between(a, b, i, n=4):
    if i == 0:
        return a
    if i == n:
        return b
    return SurfacePoint(*((x*(n-i)+y*i)//n for x, y in zip(direction(a), direction(b))))


def distance_mm(a, b, radius_m):
    return isqrt(sum((x-y)**2 for x, y in zip(direction(a), direction(b)))*(radius_m*1000)**2)//UNIT


def probe_arc_upper_mm(a, b, radius_m):
    raw = distance_mm(a, b, radius_m)
    if not raw and a == b:
        return 0
    # Account for the two normalized integer directions as well as sqrt rounding.
    chord = raw+(8*radius_m*1000+UNIT-1)//UNIT+1
    diameter = radius_m*2000
    denominator = isqrt(max(1, diameter**2-chord**2))
    return (chord*diameter+denominator-1)//denominator+1 if chord else 0


def tile_neighbor(tile, side):
    if side not in DIRECTIONS:
        raise ValueError("Unknown tile edge")
    dx, dy = {"west": (-1, 0), "east": (1, 0), "south": (0, -1), "north": (0, 1)}[side]
    n = 2**tile.level
    if 0 <= tile.x+dx < n and 0 <= tile.y+dy < n:
        return TerrainTile(tile.face, tile.level, tile.x+dx, tile.y+dy)
    point = tile.point(0 if side == "west" else 2 if side == "east" else 1,
                       0 if side == "south" else 2 if side == "north" else 1, 2)
    maximum = max(map(abs, point.xyz))
    face = next(f for f, (normal, _, _) in enumerate(BASES) if f != tile.face and
                sum(a*b for a, b in zip(normal, point.xyz)) == maximum)
    _, u, v, d = chart(point, face)
    return TerrainTile(face, tile.level, min(n-1, u*n//d), min(n-1, v*n//d))


def edge_points(tile, side, n):
    return [tile.point(0 if side == "west" else n if side == "east" else i,
                       0 if side == "south" else n if side == "north" else i, n) for i in range(1, n)]


def vertex_areas_mm2(tile, n, radius):
    """Integer midpoint cube Jacobian quadrature, NOT exact bathymetry."""
    d = 2**tile.level*n
    result = [0]*(n+1)**2
    for y in range(n):
        for x in range(n):
            u, v = 2*(tile.x*n+x)+1-d, 2*(tile.y*n+y)+1-d
            area = 4*radius**2*d*10**6//isqrt((d*d+u*u+v*v)**3)
            corners = [y*(n+1)+x, y*(n+1)+x+1, (y+1)*(n+1)+x, (y+1)*(n+1)+x+1]
            q, r = divmod(area, 4)
            for i, vertex in enumerate(corners):
                result[vertex] += q+(i < r)
    return result


def coverage_boxes(points):
    """Closed chart boxes, including all incident charts on seams/corners."""
    from fractions import Fraction
    boxes = {}
    for point in points:
        maximum = max(map(abs, point.xyz))
        for face, (normal, _, _) in enumerate(BASES):
            if sum(a*b for a, b in zip(normal, point.xyz)) != maximum:
                continue
            _, u, v, d = chart(point, face)
            a, b = Fraction(u, d), Fraction(v, d)
            if face not in boxes:
                boxes[face] = [a, a, b, b]
            else:
                old = boxes[face]
                boxes[face] = [min(old[0], a), max(old[1], a), min(old[2], b), max(old[3], b)]
    return [{"face": face, "bounds": [[v.numerator, v.denominator] for v in bounds]}
            for face, bounds in sorted(boxes.items())]
