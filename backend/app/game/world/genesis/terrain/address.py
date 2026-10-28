"""Fine subordinate addresses; no changes to the historical CellKey contract."""
from dataclasses import dataclass
from ..sphere_topology import BASES, CellKey, SurfacePoint, owning_face


def point_on_face(face, u, v, denominator):
    if (type(face) is not int or not 0 <= face < 6 or
            any(type(a) is not int for a in (u, v, denominator)) or
            not 0 < denominator <= 2**51 or not 0 <= u <= denominator or not 0 <= v <= denominator):
        raise ValueError("Invalid T1 exact face point")
    normal, axis_u, axis_v = BASES[face]
    return SurfacePoint(*(denominator*normal[i]+(2*u-denominator)*axis_u[i]+(2*v-denominator)*axis_v[i]
                          for i in range(3)))


def chart(point, face=None):
    face = owning_face(point) if face is None else face
    normal, u, v = BASES[face]
    scale = sum(a*b for a, b in zip(point.xyz, normal))
    return face, sum(a*b for a, b in zip(point.xyz, u))+scale, sum(a*b for a, b in zip(point.xyz, v))+scale, 2*scale


@dataclass(frozen=True, order=True)
class TerrainTile:
    face: int
    level: int
    x: int
    y: int

    def __post_init__(self):
        if (any(type(v) is not int for v in (self.face, self.level, self.x, self.y)) or
                not 0 <= self.face < 6 or not 0 <= self.level <= 46 or
                not 0 <= self.x < 2**self.level or not 0 <= self.y < 2**self.level):
            raise ValueError("Invalid T1 tile address")

    def parent(self, level):
        if type(level) is not int or not 0 <= level <= self.level:
            raise ValueError("Invalid T1 ancestry")
        return TerrainTile(self.face, level, self.x >> (self.level-level), self.y >> (self.level-level))

    def physical_ancestor(self, sector_level):
        if type(sector_level) is not int or not 0 <= sector_level <= 24 or sector_level > self.level:
            raise ValueError("Tile does not refine one physical sector")
        p = self.parent(sector_level)
        return CellKey(p.face, p.level, p.x, p.y)

    def point(self, x, y, intervals):
        if type(intervals) is not int or intervals not in (1, 2, 4, 8, 16, 32):
            raise ValueError("Unsupported T1 sample intervals")
        if any(type(v) is not int or not 0 <= v <= intervals for v in (x, y)):
            raise ValueError("Invalid T1 grid index")
        return point_on_face(self.face, self.x*intervals+x, self.y*intervals+y, 2**self.level*intervals)


def tile_at(point, level):
    face, u, v, d = chart(point)
    n = 2**level if type(level) is int and 0 <= level <= 46 else 0
    if not n:
        raise ValueError("Invalid T1 level")
    return TerrainTile(face, level, min(n-1, u*n//d), min(n-1, v*n//d))


def level_for_spacing(radius_m, spacing_m, intervals=16):
    if (type(radius_m) is not int or radius_m <= 0 or type(spacing_m) is not int or spacing_m <= 0 or
            type(intervals) is not int or intervals not in (1, 2, 4, 8, 16, 32)):
        raise ValueError("Positive physical spacing and supported intervals required")
    # 2R/n bounds chart-cell arc width, including the most stretched face center.
    level = 0
    while level < 46 and 2*radius_m > spacing_m*intervals*2**level:
        level += 1
    if 2*radius_m > spacing_m*intervals*2**level:
        raise ValueError("Requested spacing exceeds T1 address precision")
    return level
