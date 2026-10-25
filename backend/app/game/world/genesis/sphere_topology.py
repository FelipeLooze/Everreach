"""Exact cube charts, canonical ray addresses and edge adjacency.

Faces: +X,-X,+Y,-Y,+Z,-Z. (normal, u axis, v axis) are right handed.
Face ties use the lowest face index; this ownership never excludes a point.
"""
from dataclasses import dataclass
from math import gcd


BASES = (
    ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
    ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    ((0, 0, -1), (1, 0, 0), (0, -1, 0)),
)
DIRECTIONS = ("west", "east", "south", "north")


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


@dataclass(frozen=True)
class SurfacePoint:
    x: int
    y: int
    z: int

    def __post_init__(self):
        values = self.xyz
        if any(type(v) is not int or abs(v) > 2**53 for v in values) or not any(values):
            raise ValueError("Surface point requires a nonzero integer ray within 53 bits")
        divisor = gcd(gcd(abs(self.x), abs(self.y)), abs(self.z))
        for name, value in zip(("x", "y", "z"), values):
            object.__setattr__(self, name, value // divisor)

    @property
    def xyz(self) -> tuple[int, int, int]:
        return self.x, self.y, self.z


@dataclass(frozen=True, order=True)
class CellKey:
    face: int
    level: int
    x: int
    y: int

    def __post_init__(self):
        if any(type(v) is not int for v in (self.face, self.level, self.x, self.y)):
            raise ValueError("Cell addresses must be integers")
        if not 0 <= self.face < 6 or not 0 <= self.level <= 24:
            raise ValueError("Invalid face or cell level")
        if not (0 <= self.x < 2**self.level and 0 <= self.y < 2**self.level):
            raise ValueError("Cell index is outside its face")

    def parent(self, level: int) -> "CellKey":
        if type(level) is not int or not 0 <= level <= self.level:
            raise ValueError("Parent level must be within the cell ancestry")
        shift = self.level - level
        return CellKey(self.face, level, self.x >> shift, self.y >> shift)


def face_point(face: int, u: int, v: int, denominator: int) -> SurfacePoint:
    if (type(face) is not int or not 0 <= face < 6 or
            any(type(a) is not int for a in (u, v, denominator)) or
            not 0 < denominator <= 2**30 or not (0 <= u <= denominator and 0 <= v <= denominator)):
        raise ValueError("Invalid exact face coordinates")
    normal, axis_u, axis_v = BASES[face]
    return SurfacePoint(*(denominator * normal[i] + (2*u-denominator) * axis_u[i]
                          + (2*v-denominator) * axis_v[i] for i in range(3)))


def owning_face(point: SurfacePoint) -> int:
    maximum = max(map(abs, point.xyz))
    return next(face for face, (normal, _, _) in enumerate(BASES)
                if _dot(point.xyz, normal) == maximum)


def _cell_on_face(point: SurfacePoint, level: int, face: int) -> CellKey:
    normal, axis_u, axis_v = BASES[face]
    scale = _dot(point.xyz, normal)
    size = 2**level
    return CellKey(face, level,
                   min(size-1, (_dot(point.xyz, axis_u) + scale) * size // (2*scale)),
                   min(size-1, (_dot(point.xyz, axis_v) + scale) * size // (2*scale)))


def cell_at(point: SurfacePoint, level: int) -> CellKey:
    if type(level) is not int or not 0 <= level <= 24:
        raise ValueError("Unsupported cell level")
    return _cell_on_face(point, level, owning_face(point))


def cell_contains(key: CellKey, point: SurfacePoint) -> bool:
    """Closed cell geometry, independent of canonical seam ownership."""
    normal, axis_u, axis_v = BASES[key.face]
    scale = _dot(point.xyz, normal)
    if scale <= 0 or scale != max(map(abs, point.xyz)):
        return False
    size = 2**key.level
    u, v = ((_dot(point.xyz, axis)+scale)*size for axis in (axis_u, axis_v))
    return (2*scale*key.x <= u <= 2*scale*(key.x+1) and
            2*scale*key.y <= v <= 2*scale*(key.y+1))


def cell_center(key: CellKey) -> SurfacePoint:
    return face_point(key.face, 2*key.x+1, 2*key.y+1, 2**(key.level+1))


def cell_vertices(key: CellKey) -> tuple[SurfacePoint, ...]:
    n = 2**key.level
    return tuple(face_point(key.face, key.x+dx, key.y+dy, n)
                 for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1)))


def edge_points(key: CellKey, direction: str, intervals: int = 4) -> tuple[SurfacePoint, ...]:
    if type(intervals) is not int or intervals not in (1, 2, 4, 8, 16, 32):
        raise ValueError("Edge sample intervals must be a supported power of two")
    if direction not in DIRECTIONS:
        raise ValueError("Unknown edge direction")
    return tuple(face_point(key.face,
        key.x*intervals + (0 if direction == "west" else intervals if direction == "east" else i),
        key.y*intervals + (0 if direction == "south" else intervals if direction == "north" else i),
        2**key.level * intervals) for i in range(intervals+1))


def neighbor(key: CellKey, direction: str) -> CellKey:
    if direction not in DIRECTIONS:
        raise ValueError("Unknown edge direction")
    dx, dy = {"west": (-1, 0), "east": (1, 0), "south": (0, -1), "north": (0, 1)}[direction]
    n = 2**key.level
    if 0 <= key.x+dx < n and 0 <= key.y+dy < n:
        return CellKey(key.face, key.level, key.x+dx, key.y+dy)
    # Exact edge midpoint lies on both charts. Select the other chart normal.
    point = edge_points(key, direction, 2)[1]
    maximum = max(map(abs, point.xyz))
    face = next(f for f, (normal, _, _) in enumerate(BASES)
                if f != key.face and _dot(point.xyz, normal) == maximum)
    return _cell_on_face(point, key.level, face)


def nearby_cells(center: CellKey, radius: int = 1) -> list[CellKey]:
    """Edge graph BFS, nearest first; at most 341 visits at radius four."""
    if type(radius) is not int or not 0 <= radius <= 4:
        raise ValueError("Preparation radius must be 0..4 edge hops")
    seen, frontier, result = {center}, [center], [center]
    for _ in range(radius):
        layer = {neighbor(key, direction) for key in frontier for direction in DIRECTIONS} - seen
        frontier = sorted(layer)
        result.extend(frontier)
        seen.update(layer)
    return result
