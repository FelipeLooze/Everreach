"""Offline C1 diagnostics; visualization floats never affect climate authority."""
import json
from pathlib import Path

from PIL import Image, ImageDraw

from ..sphere_area import rectangle_solid_angle
from ..sphere_topology import face_point
from .geometry import geometry
from .physics import lapse, pet_milli_mm_day
from .query import sample_climate


def metrics(plan):
    g, n = geometry(plan.config.level), 2**plan.config.level
    areas = [0.0]*len(g.points)
    for face in g.faces:
        for y in range(n):
            for x in range(n):
                weight = rectangle_solid_angle(2*x/n-1, 2*y/n-1, 2*(x+1)/n-1, 2*(y+1)/n-1)/4
                for dx, dy in ((0, 0), (0, 1), (1, 0), (1, 1)):
                    areas[face[(y+dy)*(n+1)+x+dx]] += weight
    temperatures, rain, ranges, aridity = [], [], [], []
    for i, height in enumerate(plan.heights):
        ts = [lapse(plan.sea_temperature_centi_c[s][i], height-plan.sea_level_m, plan.config) for s in range(4)]
        p = sum(plan.precipitation_mm[s][i] for s in range(4))
        pet = sum(pet_milli_mm_day(ts[s], plan.insolation_ppm[s][i], plan.config)*plan.config.year_days//4000 for s in range(4))
        temperatures.append(sum(ts)//4)
        rain.append(p)
        ranges.append(max(ts)-min(ts))
        aridity.append(max(0, pet-p)*1_000_000//pet if pet else 0)
    total = sum(areas)
    land_area = sum(a for a, h in zip(areas, plan.heights) if h >= plan.sea_level_m)
    return {"signature": plan.signature, "source_signature": plan.source_signature, "hydrology_signature": plan.hydrology_signature,
        "radius_m": plan.radius_m, "config": plan.config.model_dump(), "vertices": len(g.points),
        "surface_area_weighting": "exact_cube_cell_solid_angle_quarter_distributed_to_vertices",
        "weighted_land_fraction": land_area/total,
        "weighted_mean_temperature_c": sum(a*t for a, t in zip(areas, temperatures))/total/100,
        "weighted_annual_precipitation_mm": sum(a*p for a, p in zip(areas, rain))/total,
        "weighted_land_dry_fraction_aridity_above_0_75": sum(a for a, h, dry in zip(areas, plan.heights, aridity)
            if h >= plan.sea_level_m and dry > 750_000)/land_area if land_area else None,
        "annual_mean_temperature_range_c": [min(temperatures)/100, max(temperatures)/100],
        "annual_precipitation_range_mm": [min(rain), max(rain)],
        "seasonal_temperature_range_c": [min(ranges)/100, max(ranges)/100],
        "transport_residual_ppm": list(plan.transport_residual_ppm),
        "effective_maritime_length_m": plan.maritime_length_m, "effective_moisture_length_m": plan.moisture_length_m,
        "actual_runoff_or_permanent_water": "not_modeled"}


def _mix(a, b, fraction):
    fraction = max(0.0, min(1.0, fraction))
    return tuple(round(x+(y-x)*fraction) for x, y in zip(a, b))


def temperature_color(centi):
    if centi < 0:
        return _mix((25, 45, 130), (218, 240, 245), (centi+6000)/6000)
    if centi < 2500:
        return _mix((218, 240, 245), (245, 208, 92), centi/2500)
    return _mix((245, 208, 92), (188, 48, 38), (centi-2500)/2500)


def precipitation_color(mm):
    if mm < 500:
        return _mix((100, 67, 48), (220, 201, 143), mm/500)
    if mm < 1500:
        return _mix((220, 201, 143), (64, 150, 96), (mm-500)/1000)
    return _mix((64, 150, 96), (73, 191, 240), (mm-1500)/2000)


def write_preview(plan, output: Path, sample_size=48):
    if type(sample_size) is not int or not 16 <= sample_size <= 96:
        raise ValueError("C1 developer sample size must be 16..96")
    output.mkdir(parents=True, exist_ok=True)
    size, pad, header, footer = 192, 16, 72, 74
    width, height = 3*size+4*pad, 2*(size+24)+header+footer
    names = ("temperature", "precipitation", "season_1", "season_3")
    panels = {name: Image.new("RGB", (width, height), (17, 23, 32)) for name in names}
    for face in range(6):
        tiles = {name: Image.new("RGB", (sample_size, sample_size)) for name in names}
        for y in range(sample_size):
            for x in range(sample_size):
                point = face_point(face, 2*x+1, 2*y+1, 2*sample_size)
                sample = sample_climate(plan, point)
                pixel = x, sample_size-1-y
                tiles["temperature"].putpixel(pixel, temperature_color(sample["mean_temperature_centi_c"]))
                tiles["precipitation"].putpixel(pixel, precipitation_color(sample["annual_precipitation_mm"]))
                for season in (1, 3):
                    tiles[f"season_{season}"].putpixel(pixel, temperature_color(sample["seasons"][season]["temperature_centi_c"]))
        origin = pad+(face%3)*(size+pad), header+(face//3)*(size+24)
        for name, panel in panels.items():
            panel.paste(tiles[name].resize((size, size), Image.Resampling.NEAREST), origin)
            ImageDraw.Draw(panel).text((origin[0], origin[1]-18), f"Face {face}", fill="white")
    captions = {"temperature": "Annual mean temperature (C)", "precipitation": "Annual climatological precipitation (mm)",
                "season_1": "Period 1 temperature / northern summer", "season_3": "Period 3 temperature / southern summer"}
    for name, panel in panels.items():
        draw = ImageDraw.Draw(panel)
        draw.text((pad, 10), f"EVERREACH / C{plan.config.climate_version} / {captions[name]}", fill="white")
        draw.text((pad, 30), f"R={plan.radius_m/1000:g} km | {len(plan.heights)} vertices | OFFLINE DEV ONLY", fill=(200, 215, 230))
        draw.text((pad, height-footer+5), "T: dark blue -60 / pale 0 / yellow +25 / red +50 C", fill=(220, 230, 240))
        draw.text((pad, height-footer+23), "P: brown 0 / sand 500 / green 1500 / blue 3500 mm/year", fill=(220, 230, 240))
        draw.text((pad, height-footer+41), "Climatology only. No daily weather, runoff or permanent rivers/lakes.", fill=(220, 230, 240))
        panel.save(output/f"{name}.png")
    atlas = Image.new("RGB", (2*width, 2*height))
    for i, panel in enumerate(panels.values()):
        atlas.paste(panel, ((i%2)*width, (i//2)*height))
    atlas.save(output/"climate.png")


def write_summary(plan, output, benchmark):
    result = {**metrics(plan), "benchmark": benchmark}
    (output/"summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
