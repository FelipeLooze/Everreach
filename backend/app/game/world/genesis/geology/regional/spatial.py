"""Integer sphere/box sites; fixed 343-box halo, independent of planetary area."""
from collections import OrderedDict
from itertools import product
from functools import lru_cache
from math import isqrt
from ...terrain.field import _direction, PRECISION, checksum
from ...sphere_topology import SurfacePoint

Q = 2**80


@lru_cache(maxsize=32768)
def position_mm(point,radius):
    return tuple(v*radius*1000//PRECISION for v in _direction(point))


def box_site(key,spacing,radius,signature):
    low = [k*spacing for k in key]
    high = [(k+1)*spacing for k in key]
    near = [0 if a<=0<=b else min((a,b),key=abs) for a,b in zip(low,high)]
    far = [max((a,b),key=lambda v:(abs(v),v)) for a,b in zip(low,high)]
    squared = lambda p:sum(v*v for v in p)
    r2 = radius*radius
    if not squared(near)<r2<squared(far):
        return None  # tangent boxes have no positive-area surface
    ticket = int(checksum([signature,"site",key])[:24],16)
    trial = [a+(b-a)*(1+(ticket>>(i*8))%254)//256 for i,(a,b) in enumerate(zip(near,far))]
    # Perturb the chord within its box, retaining opposite sides of the sphere.
    if squared(trial)<r2:
        near = trial
    elif squared(trial)>r2:
        far = trial
    delta = [b-a for a,b in zip(near,far)]
    a = squared(delta)
    b = 2*sum(x*y for x,y in zip(near,delta))
    c = squared(near)-r2
    t = (-b*Q+isqrt((b*b-4*a*c)*Q*Q))//(2*a)
    ray = tuple(v*Q+d*t for v,d in zip(near,delta))
    maximum = max(map(abs,ray))
    # Preserve the existing exact-ray 53-bit contract; <1 mm at max radius.
    return SurfacePoint(*(v*2**52//maximum for v in ray))


class PhysicalSites:
    def __init__(self,radius,spacing,signature):
        self.radius = radius
        self.spacing = min(spacing,max(1,radius//4))
        self.signature = signature
        self.cache = OrderedDict()
        self.site_builds = 0

    def site(self,key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        value = box_site(key,self.spacing,self.radius,self.signature)
        self.site_builds += 1
        self.cache[key] = value
        while len(self.cache)>4096:
            self.cache.popitem(last=False)
        return value

    def nearest(self,point):
        xyz = position_mm(point,self.radius)
        owner = tuple(v//(self.spacing*1000) for v in xyz)
        best = None
        for offset in product(range(-3,4),repeat=3):
            key = tuple(c+d for c,d in zip(owner,offset))
            site = self.site(key)
            if site is None:
                continue
            p = position_mm(site,self.radius)
            candidate = sum((a-b)**2 for a,b in zip(p,xyz)),key
            if best is None or candidate<best[0]:
                best = candidate,site
        if best is None:
            raise ValueError("JR1 positive-area site coverage failed")
        return best[0][1],best[1]
