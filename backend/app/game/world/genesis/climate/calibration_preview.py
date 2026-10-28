"""Paired technical C1/C2 fields; no public map or habitat assignment."""
from PIL import Image, ImageDraw

from ..sphere_topology import face_point
from .preview import _mix, temperature_color, precipitation_color
from .query import sample_climate


def aridity_color(value):
    if value is None:
        return 115, 122, 135
    if value < 500_000:
        return _mix((38, 145, 170), (225, 220, 124), value/500_000)
    return _mix((225, 220, 124), (115, 57, 37), (value-500_000)/500_000)


def write_comparison(c1, c2, output, seed, sample_size=32):
    if not 16 <= sample_size <= 64:
        raise ValueError("Calibration atlas samples must be 16..64 per face")
    if (c1.source_signature != c2.source_signature or c1.hydrology_signature != c2.hydrology_signature
            or c1.config.climate_version != 1 or c2.config.climate_version != 2):
        raise ValueError("Comparison requires paired C1/C2 from the same terrain and H1")
    output.mkdir(parents=True, exist_ok=True)
    size, pad, top, width, height = 160, 16, 76, 544, 520
    names = ("temperature", "precipitation", "aridity", "period_1_temperature", "period_3_temperature",
             "period_1_precipitation", "period_3_precipitation")
    panels = {name: Image.new("RGB", (2*width, height), (17, 23, 32)) for name in names}
    for column, plan in enumerate((c1, c2)):
        for face in range(6):
            tiles = {name: Image.new("RGB", (sample_size, sample_size)) for name in names}
            for y in range(sample_size):
                for x in range(sample_size):
                    sample = sample_climate(plan, face_point(face, 2*x+1, 2*y+1, 2*sample_size))
                    point = x, sample_size-y-1
                    tiles["temperature"].putpixel(point, temperature_color(sample["mean_temperature_centi_c"]))
                    tiles["precipitation"].putpixel(point, precipitation_color(sample["annual_precipitation_mm"]))
                    tiles["aridity"].putpixel(point, aridity_color(sample["aridity_index_ppm"]))
                    for season in (1, 3):
                        tiles[f"period_{season}_temperature"].putpixel(point, temperature_color(sample["seasons"][season]["temperature_centi_c"]))
                        tiles[f"period_{season}_precipitation"].putpixel(point, precipitation_color(4*sample["seasons"][season]["precipitation_mm"]))
            origin = column*width+pad+(face%3)*(size+pad), top+(face//3)*(size+24)
            for name, panel in panels.items():
                panel.paste(tiles[name].resize((size, size), Image.Resampling.NEAREST), origin)
                ImageDraw.Draw(panel).text((origin[0], origin[1]-16), f"Face {face}", fill="white")
        for name, panel in panels.items():
            draw = ImageDraw.Draw(panel)
            x = column*width+pad
            draw.text((x, 10), f"EVERREACH / C{plan.config.climate_version} / seed {seed} / {name}", fill="white")
            draw.text((x, 29), f"R={plan.radius_m/1000:g} km | level {plan.config.level} | OFFLINE ONLY", fill=(200, 215, 230))
            draw.text((x, height-64), "T: -60 blue / 0 pale / +25 yellow / +50 red C", fill=(220, 230, 240))
            draw.text((x, height-47), "P: 0 brown / 500 sand / 1500 green / 3500 blue mm", fill=(220, 230, 240))
            draw.text((x, height-30), "Period P uses annual-equivalent 4x the period total.", fill=(220, 230, 240))
            draw.text((x, height-13), "Aridity: 0 cyan / 1 brown; grey = PET zero. NO BIOMES.", fill=(220, 230, 240))
    for name, panel in panels.items():
        panel.save(output/f"{name}-comparison.png")
