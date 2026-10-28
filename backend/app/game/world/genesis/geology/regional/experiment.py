"""Offline physical windows and diagnostics; never an exploration/gameplay API."""
from itertools import product
from math import isqrt
from ...terrain.field import _direction,PRECISION
from ...sphere_topology import SurfacePoint
from ...sphere_area import _triangle_area
from .spatial import position_mm


def axes(center):
    normal = _direction(center)
    i = min(range(3),key=lambda k:abs(normal[k]))
    ref = tuple(PRECISION if k==i else 0 for k in range(3))
    def cross(a,b):
        return a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]
    def unit(a):
        length = isqrt(sum(v*v for v in a))
        return tuple(v*PRECISION//length for v in a)
    east = unit(cross(normal,ref))
    return normal,east,unit(cross(normal,east))


def window_point(center,x_m,y_m,radius):
    n,a,b = axes(center)
    ray = tuple(v+(x*x_m+y*y_m)//radius for v,x,y in zip(n,a,b))
    maximum = max(map(abs,ray))
    return SurfacePoint(*(v*2**52//maximum for v in ray))


def window_coordinates(center,point,radius):
    n,a,b = axes(center)
    d = _direction(point)
    den = sum(x*y for x,y in zip(n,d))
    if den<=0:
        return None
    return tuple(sum(x*y for x,y in zip(axis,d))*radius//den for axis in (a,b))


def window_formations(sampler,center,width_m=96000):
    if type(width_m) is not int or not 0<width_m<=128000 or width_m>sampler.sites.radius//2:
        raise ValueError("Offline window must be <=128 km and local to the sphere")
    half = width_m//2
    rays = [window_point(center,x,y,sampler.sites.radius) for x,y in product((-half,0,half),repeat=2)]
    xyz = [position_mm(p,sampler.sites.radius) for p in rays]
    spacing = sampler.sites.spacing*1000
    ranges = [range(min(p[i] for p in xyz)//spacing-2,max(p[i] for p in xyz)//spacing+3) for i in range(3)]
    count = len(ranges[0])*len(ranges[1])*len(ranges[2])
    if count>16000:
        raise ValueError("Offline enumeration budget exceeded")
    formations = {}
    for key in product(*ranges):
        site = sampler.sites.site(key)
        if site is None:
            continue
        xy = window_coordinates(center,site,sampler.sites.radius)
        if xy is not None and -half<=xy[0]<half and -half<=xy[1]<half:
            f = sampler.formation(site)
            formations[f["formation_id"]] = f
    return formations,{"enumerated_boxes":count,"width_m":width_m,"selection":"all_anchors_in_physical_window_no_mineral_filter"}


def measure_window(sampler,center,width_m=96000,intervals=24):
    half,step = width_m//2,width_m//intervals
    area=land=prospectable=0.0
    groups = {}
    raster = []
    from ...terrain.address import tile_at
    for y in range(intervals):
        row = []
        for x in range(intervals):
            x0,y0 = -half+x*step,-half+y*step
            p = window_point(center,x0+step//2,y0+step//2,sampler.sites.radius)
            f = sampler.formation(p)
            row.append(f["formation_id"])
            groups.setdefault(f["formation_id"],[]).append({"point":list(p.xyz),
                "sector":list(vars(tile_at(p,sampler.terrain.plan.source.config.sector_level)).values())})
            a,b,c,d = [window_point(center,*xy,sampler.sites.radius).xyz for xy in
                ((x0,y0),(x0+step,y0),(x0+step,y0+step),(x0,y0+step))]
            weight = (_triangle_area(a,b,c)+_triangle_area(a,c,d))*sampler.sites.radius**2
            area += weight
            terrain = sampler.terrain.sample(p)
            if terrain["height_mm"]>sampler.terrain.plan.source.config.sea_level_m*1000:
                land += weight
                if terrain["slope_proxy_ppm"]<=300000:
                    prospectable += weight
        raster.append(row)
    witness = next(([a,b] for points in groups.values() for a in points for b in points if a["sector"]!=b["sector"]),None)
    return {"area_km2":area/1e6,"land_area_km2":land/1e6,"gentle_land_proxy_km2":prospectable/1e6,
        "coverage_intervals":intervals,"grid_touched_formations":len(groups),
        "cross_sector_witness":witness,"raster":raster}


def cross_sector_points(sampler,formation):
    from ...terrain.address import tile_at
    center=SurfacePoint(*formation["anchor_point"])
    first=None
    step=max(1,sampler.sites.spacing//5)
    for x,y in product(range(-3,4),repeat=2):
        p=window_point(center,x*step,y*step,sampler.sites.radius)
        if sampler.address(p)[3]!=formation["formation_id"]:
            continue
        sector=list(vars(tile_at(p,sampler.terrain.plan.source.config.sector_level)).values())
        view={"point":list(p.xyz),"sector":sector}
        if first is None:
            first=view
        elif first["sector"]!=sector:
            return [first,view]
    return None
