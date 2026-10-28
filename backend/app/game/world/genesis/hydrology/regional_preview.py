"""Developer comparison of H1 representatives and HR1 sampled candidates."""
from pathlib import Path

from PIL import Image, ImageDraw

from ..formation_preview import terrain_color
from ..sphere_topology import CellKey, SurfacePoint
from .regional_graph import SampleContext
from .sectors import _face_uv, sector_snapshot


def write_regional_preview(source, h1, region, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    key, size, pad, top = CellKey(*region["tile"]), 352, 20, 94
    width, height = 2*size+3*pad, size+top+136
    image = Image.new("RGB", (width, height), (17, 23, 32))
    draw = ImageDraw.Draw(image)
    graph = SampleContext(source, region["config"]["depth"]).graph(key)
    n, span = 2**region["config"]["depth"], 2**key.level
    def pixel(point, panel):
        u, v = _face_uv(point, key.face)
        x, y = (float(u+1)*span/2-key.x)*size, (float(v+1)*span/2-key.y)*size
        return round(pad+panel*(size+pad)+x), round(top+size-y)
    # Nearest sampled vertex color, explicitly a discrete terrain diagnostic.
    for panel in (0, 1):
        for i, (x, y) in enumerate(graph.coordinates):
            px, py = pixel(graph.points[i], panel)
            half = size//(2*n)
            ox = pad+panel*(size+pad)
            box = max(ox, px-half), max(top, py-half), min(ox+size, px+half), min(top+size, py+half)
            draw.rectangle(box, fill=terrain_color(graph.heights[i], source.config.sea_level_m))
    for corridor in sector_snapshot(h1, key)["corridors"]:
        draw.line([pixel(SurfacePoint(*p), 0) for p in corridor["points"]], fill=(235, 235, 235), width=3)
    for segment in region["segments"]:
        a, b = (pixel(SurfacePoint(*p), 1) for p in segment["points"])
        color = (255, 172, 55) if any(segment["storage_raise_m"]) else (70, 235, 255)
        draw.line((a, b), fill=color, width=3)
        # A small downstream dot distinguishes direction without inventing flow.
        draw.ellipse((b[0]-2, b[1]-2, b[0]+2, b[1]+2), fill=color)
    for port in region["ports"]:
        for panel, field in ((0, "h1_representative_port"), (1, "point")):
            x, y = pixel(SurfacePoint(*port[field]), panel)
            color = (255, 90, 90) if port["status"] != "sampled_pair_compatible" else (250, 245, 160)
            draw.ellipse((x-4, y-4, x+4, y+4), outline=color, width=2)
    for panel in (0, 1):
        x, y = pixel(SurfacePoint(*region["junction"]["point"]), panel)
        draw.ellipse((x-5, y-5, x+5, y+5), fill=(255, 255, 255), outline=(30, 30, 30))
    draw.text((pad, 12), f"EVERREACH / HR1 / seed {source.seed} / R={source.config.radius_m/1000:g} km", fill="white")
    draw.text((pad, 31), f"H1 node {region['node']} / face {key.face} / depth {region['config']['depth']} / OFFLINE ONLY", fill="white")
    draw.text((pad, 50), f"V4 detail wavelength: {region['terrain_detail_wavelength_m']/1000:g} km (no new terrain)", fill=(195, 210, 225))
    draw.text((pad, 74), "H1 macro representatives", fill="white")
    draw.text((2*pad+size, 74), "HR1 regional sampled potential", fill="white")
    lines = (f"Prepared: {len(region['segments'])} segments | {len(region['issues'])} unresolved route issues.",
        "White: H1 corridor. Cyan: sampled downhill. Orange: storage head required.",
        "Yellow port: pair-compatible; red port: H1 head cannot clear sampled terrain.",
        "Background: sampled V4 vertices. Grid detail is NOT a metre-scale river bed.",
        "Routes still require peer/subgrid checks. Water, discharge and permanence UNKNOWN.")
    for i, line in enumerate(lines):
        draw.text((pad, top+size+16+19*i), line, fill=(220, 230, 240))
    image.save(output/"regional.png")
