"""Static kinematic reconstruction, not a time-stepped geophysical simulation."""
from math import isqrt

from .formation_config import FormationConfig, calibrated_scale
from .formation_noise import UNIT, cross, dot, noise, unit_direction
from .formation_plates import Plate
from .sphere_topology import SurfacePoint


def profile(distance_m: int, width_m: int) -> int:
    """Compact, smooth shoulder; UNIT at its center and zero outside its width."""
    if abs(distance_m) >= width_m:
        return 0
    return (width_m*width_m-distance_m*distance_m)**2*UNIT//width_m**4


def evaluate(seed: int, config: FormationConfig, plates: tuple[Plate, ...],
             point: SurfacePoint, *, causes: bool = True) -> dict:
    direction = unit_direction(point)
    scale = calibrated_scale(config)
    length, width = scale["plate_length_m"], scale["orogen_width_m"]
    # A shared low-frequency deformation avoids polygonal coasts/orogens.
    # This is a static reconstructed domain, not physical integration of rigid plates.
    warp = tuple(noise(seed, direction, config.radius_m, max(1, length//2), f"crust_deformation_{i}")
                 *length*UNIT*35//(10_000*config.radius_m*100) for i in range(3))
    crust_direction = unit_direction(SurfacePoint(*(v+w for v, w in zip(direction, warp))))
    scores = [(dot(plate.center, crust_direction), plate) for plate in plates]
    maximum = max(score for score, _ in scores)
    # Compact influence depends only on the continuous maximum score, not the
    # identity of the winning site. This also remains continuous at triple junctions.
    support = max(1, UNIT**2*length**2//(8*config.radius_m**2))
    active = [(plate, (support-(maximum-score))**2, score) for score, plate in scores
              if maximum-score < support]
    total = sum(weight for _, weight, _ in active)
    continental = sum(weight for plate, weight, _ in active if plate.continental)*1_000_000//total
    buoyancy = sum(weight*((1000+plate.age_myr*3) if plate.continental else (-4000-plate.age_myr*6))
                   for plate, weight, _ in active)//total
    mantle = noise(seed, direction, config.radius_m, length, "mantle_swell")*1600//10_000
    regional_noise = noise(seed, direction, config.radius_m, scale["regional_wavelength_m"], "regional_isostasy")
    regional = regional_noise*500//10_000
    fine_noise = noise(seed, direction, config.radius_m, scale["detail_wavelength_m"], "local_relief")
    tectonic = 0
    structures = []
    velocities = {p.slot: tuple(v*p.speed_mm_year//UNIT for v in cross(p.axis, crust_direction)) for p, _, _ in active}
    for i, (a, wa, sa) in enumerate(active):
        for b, wb, sb in active[i+1:]:
            normal = tuple(x-y for x, y in zip(a.center, b.center))
            norm = max(1, isqrt(dot(normal, normal)))
            relative = tuple(y-x for x, y in zip(velocities[a.slot], velocities[b.slot]))
            # Rates stay in fixed-point until final metre rounding. Rounding
            # motion to whole mm/year here would create ~100 m height steps.
            closing = dot(relative, normal)//norm
            compression, extension = min(100*UNIT, max(0, closing)), min(100*UNIT, max(0, -closing))
            shear = min(100*UNIT, max(0, isqrt(dot(relative, relative))-abs(closing)))
            signed_distance = (sa-sb)*config.radius_m//(norm*UNIT)
            line = profile(signed_distance, width)
            broad = profile(signed_distance, 4*width)
            weight = 4*wa*wb*UNIT//total**2
            if a.continental and b.continental:
                uplift = compression*(7000*line+2000*broad)//(100*UNIT**2)
                subsidence = extension*1800*line//(100*UNIT**2)
                mechanism = "continental_collision" if closing >= 0 else "continental_rift"
            elif a.continental or b.continental:
                # Signed distance toward the overriding continental side.
                overriding = signed_distance if a.continental else -signed_distance
                arc = profile(overriding-width, 2*width)
                trench = profile(overriding+width//3, max(1, width//2))
                uplift = compression*7500*arc//(100*UNIT**2)
                subsidence = compression*3500*trench//(100*UNIT**2)
                mechanism = "subduction_arc" if closing >= 0 else "continental_margin_rift"
                subsidence += extension*1200*line//(100*UNIT**2)
            else:
                # Older oceanic crust subducts below the younger plate.
                overriding = signed_distance if (a.age_myr, a.slot) < (b.age_myr, b.slot) else -signed_distance
                arc = profile(overriding-width, 2*width)
                trench = profile(overriding+width//3, max(1, width//2))
                uplift = (compression*11_000*arc+extension*2800*line)//(100*UNIT**2)
                subsidence = compression*3000*trench//(100*UNIT**2)
                mechanism = "island_arc" if closing >= 0 else "ocean_spreading_ridge"
            fault = shear*500*line*regional_noise//(100*UNIT**2*10_000)
            if shear > 4*abs(closing) and shear > UNIT:
                mechanism = "transform_fault"
            contribution = (uplift-subsidence+fault)*weight//UNIT
            tectonic += contribution
            if causes and weight > 0:
                slots = sorted((a.slot, b.slot))
                structures.append({"plates": slots, "mechanism": mechanism,
                    "closing_micro_mm_year": closing*1_000_000//UNIT,
                    "shear_micro_mm_year": shear*1_000_000//UNIT,
                    "contribution_m": contribution,
                    "boundary_distance_m": signed_distance, "fault_relief_m": fault*weight//UNIT,
                    "uplift_m": uplift*weight//UNIT, "subsidence_m": subsidence*weight//UNIT})
    detail = fine_noise*(100+max(0, tectonic)//3)//10_000
    dominant = min(((-score, plate.slot) for score, plate in scores))[1]
    return {"elevation_m": buoyancy+mantle+regional+tectonic+detail,
            "dominant_plate": dominant, "continental_crust_ppm": continental,
            "terms_m": {"crust_buoyancy": buoyancy, "mantle_swell": mantle,
                        "regional_isostasy": regional, "tectonic": tectonic, "detail": detail},
            "structures": structures}
