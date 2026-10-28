"""K1 integer Manning estimate with explicit finite wetting volume and limits."""
from fractions import Fraction
from math import isqrt
from ...sphere_topology import SurfacePoint
from ...hydro_geometry.spatial import direction, UNIT, distance_mm, between


def icbrt(value):
    if value < 0:
        raise ValueError("Negative cube-root argument")
    low, high = 0, 1 << ((value.bit_length()+2)//3)
    while low < high:
        mid = (low+high+1)//2
        if mid**3 <= value:
            low = mid
        else:
            high = mid-1
    return low


def section_at_depth(zs, step_mm, depth_mm):
    middle = len(zs)//2
    level = zs[middle]+depth_mm
    area, perimeter, width = Fraction(0), Fraction(0), Fraction(0)
    for sign in (-1, 1):
        i = middle
        while 0 <= i+sign < len(zs):
            a, b = zs[i], zs[i+sign]
            if b >= level:
                fraction = Fraction(level-a, b-a) if b > a else Fraction(0)
                extent = fraction*step_mm
                area += (level-a)*extent/2
                perimeter += fraction*(isqrt(step_mm**2+(b-a)**2)+1)
                width += extent
                break
            area += Fraction((2*level-a-b)*step_mm, 2)
            perimeter += isqrt(step_mm**2+(b-a)**2)+1
            width += step_mm
            i += sign
        else:
            return None
    return {"area_mm2": int(area), "wetted_perimeter_mm": int(perimeter), "width_mm": int(width), "depth_mm": depth_mm}


def transverse_points(point, downstream, radius, config):
    a, b = direction(point), direction(downstream)
    normal = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    norm = isqrt(sum(v*v for v in normal))
    if not norm:
        return None
    normal = tuple(v*UNIT//norm for v in normal)
    return [point if i == 0 else SurfacePoint(*(v+n*i*config.cross_step_mm//(radius*1000) for v, n in zip(a, normal)))
            for i in range(-config.cross_half_intervals, config.cross_half_intervals+1)]


def transverse(context, point, downstream, radius, config):
    points = transverse_points(point, downstream, radius, config)
    if points is None:
        return None
    zs = [context.height(p) for p in points]
    crest = min(max(zs[:len(zs)//2]), max(zs[len(zs)//2+1:]))
    return {"points": [list(p.xyz) for p in points], "terrain_mm": zs, "bank_room_mm": crest-zs[len(zs)//2]}


def capacity(sections, points, heights, depth_mm, slope_drop_mm, config):
    length = sum(distance_mm(a, b, config["radius_m"]) for a, b in zip(points, points[1:]))
    policy = config["policy"]
    if length <= 0 or slope_drop_mm <= 0 or depth_mm < 2:
        return None
    shapes = [section_at_depth(s["terrain_mm"], policy.cross_step_mm, depth_mm) for s in sections]
    if any(s is None or s["area_mm2"] <= 0 or s["wetted_perimeter_mm"] <= 0 for s in shapes):
        return None
    q_values = []
    for shape in shapes:
        radius_mm = shape["area_mm2"]//shape["wetted_perimeter_mm"]
        radius_power_q = icbrt(radius_mm**2*10**18//10**6)
        slope_q = isqrt(slope_drop_mm*10**12//length)
        velocity = min(policy.velocity_limit_mm_s, radius_power_q*slope_q*10**6//(10**12*policy.manning_n_milli))
        q_values.append(shape["area_mm2"]*velocity*policy.capacity_factor_ppm//10**6)  # mm3/s
    q_mm3_s = min(q_values)
    wet_volume_mm3 = sum((a["area_mm2"]+b["area_mm2"])*distance_mm(pa, pb, config["radius_m"])//2
                         for a, b, pa, pb in zip(shapes, shapes[1:], points, points[1:]))
    return {"capacity_version": 1, "model": "integer_Manning_derated_RPG_estimate", "depth_mm": depth_mm,
            "sections": shapes, "length_mm": length, "hydraulic_drop_mm": slope_drop_mm,
            "q_mm3_s": q_mm3_s, "episode_capacity_liters": q_mm3_s*policy.episode_minutes*60//10**6,
            "required_wetting_liters": (wet_volume_mm3+10**6-1)//10**6,
            "roughness_n_milli": policy.manning_n_milli, "velocity_limit_mm_s": policy.velocity_limit_mm_s,
            "capacity_factor_ppm": policy.capacity_factor_ppm, "scientific_certification": False}
