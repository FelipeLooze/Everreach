"""Offline diagnostics of H1 potential, never a player map or wet-state model."""
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from ..formation_plan import indexed_cell
from ..formation_preview import terrain_color
from ..sphere_metric import distance_m
from .geometry import geometry
from .plan import HydrologyPlan
from .sectors import _face_uv


def metrics(plan: HydrologyPlan, source_config) -> dict:
    g, d = geometry(plan.config.level), plan.drainage
    lengths = [0.0]*len(g.points)
    for node in sorted(range(len(g.points)), key=lambda n: d.rank[n]):
        parent = d.parent[node]
        if parent >= 0:
            edge = g.edge_lookup[tuple(sorted((node, parent)))]
            lengths[node] = lengths[parent] + sum(distance_m(source_config, a, b)
                for a, b in zip((g.points[node], g.ports[edge]), (g.ports[edge], g.points[parent])))
    total = sum(plan.cell_area_m2)
    return {"hydrology_signature": plan.signature, "source_signature": plan.source_signature,
        "radius_m": plan.radius_m, "level": plan.config.level, "nodes": len(g.points), "edges": len(g.edges),
        "distinct_terrain_samples": len({p for profile in g.profiles for p in profile}),
        "area_weighted_land_fraction": sum(a for a, z in zip(plan.cell_area_m2, plan.heights)
            if z >= plan.sea_level_m)/total,
        "reference_ocean_area_fraction": sum(a for a, m in zip(plan.cell_area_m2, d.marine) if m)/total,
        "potential_reaches": len(plan.reaches), "potential_basins_by_outlet": len(plan.basin_records()),
        "macro_divides": len(plan.divide_records()), "closed_raw_basins": len(plan.closed_basin_records()),
        "depression_storage_candidates": len(d.depressions),
        "potential_cross_face_edges": sum(indexed_cell(i, plan.config.level).face !=
            indexed_cell(d.parent[i], plan.config.level).face for i in plan.channel_index),
        "max_conditioned_path_km": round(max(lengths)/1000, 3),
        "max_potential_strahler_order": max(d.order),
        "raised_nonmarine_nodes": sum(not m and h > z for m, h, z in zip(d.marine, d.head, plan.heights)),
        "height_range_m": [min(plan.heights), max(plan.heights)],
        "area_conserved": sum(d.area[i] for i, p in enumerate(d.parent) if p < 0) ==
            sum(a for a, m in zip(plan.cell_area_m2, d.marine) if not m),
        "water_balance": "not_modeled", "actual_fed_watercourses": None,
        "geometry_status": "macro_potential_not_final_river_beds"}


def write_preview(plan: HydrologyPlan, output: Path, face_size: int = 192) -> None:
    if type(face_size) is not int or not 128 <= face_size <= 512:
        raise ValueError("Hydrology preview face size must be 128..512")
    output.mkdir(parents=True, exist_ok=True)
    pad, header, footer = 16, 76, 88
    width, height = 3*(face_size+pad)+pad, 2*(face_size+28)+header+footer
    panels = [Image.new("RGB", (width, height), (17, 23, 32)) for _ in range(2)]
    g, d, n = geometry(plan.config.level), plan.drainage, 2**plan.config.level
    def origin(face):
        return pad+(face%3)*(face_size+pad), header+(face//3)*(face_size+28)
    def pixel(point, face):
        u, v = _face_uv(point, face)
        ox, oy = origin(face)
        return ox+round(float(u+1)*(face_size-1)/2), oy+round(float(1-v)*(face_size-1)/2)
    for node, z in enumerate(plan.heights):
        key = indexed_cell(node, plan.config.level)
        ox, oy = origin(key.face)
        box = (ox+key.x*face_size//n, oy+(n-1-key.y)*face_size//n,
               ox+(key.x+1)*face_size//n-1, oy+(n-key.y)*face_size//n-1)
        ImageDraw.Draw(panels[0]).rectangle(box, fill=terrain_color(z, plan.sea_level_m))
        digest = hashlib.sha256(plan.identifier("basin", d.outlet[node]).encode()).digest()
        color = (15, 46, 77) if d.marine[node] else tuple(45+b//3 for b in digest[:3])
        ImageDraw.Draw(panels[1]).rectangle(box, fill=color)
    for node in plan.channel_index:
        target = d.parent[node]
        edge = g.edge_lookup[tuple(sorted((node, target)))]
        conditional = any(plan.edge_record(node)["raise_above_sampled_terrain_m"])
        color = (255, 165, 58) if conditional else (65, 231, 255)
        line_width = 2 if d.area[node] >= plan.major_threshold_m2 else 1
        for a, b, face in ((g.points[node], g.ports[edge], indexed_cell(node, plan.config.level).face),
                           (g.ports[edge], g.points[target], indexed_cell(target, plan.config.level).face)):
            for panel in panels:
                ImageDraw.Draw(panel).line((pixel(a, face), pixel(b, face)), fill=color, width=line_width)
    for pool in d.depressions:
        node = min(pool, key=lambda i: (plan.heights[i], i))
        face = indexed_cell(node, plan.config.level).face
        x, y = pixel(g.points[node], face)
        ImageDraw.Draw(panels[1]).ellipse((x-2, y-2, x+2, y+2), outline=(255, 240, 170))
    for panel, name in zip(panels, ("terrain", "basins")):
        draw = ImageDraw.Draw(panel)
        draw.text((pad, 10), f"EVERREACH / H1 POTENTIAL DRAINAGE / {name.upper()}", fill="white")
        draw.text((pad, 28), f"R={plan.radius_m/1000:g} km | H level {plan.config.level} | {len(g.points)} nodes", fill="white")
        draw.text((pad, 46), f"Source V4: {plan.source_signature} | OFFLINE DEVELOPER ONLY", fill=(180, 195, 210))
        for face in range(6):
            x, y = origin(face)
            draw.text((x, y-18), f"Face {face}", fill="white")
        for row, text in enumerate(("Cyan: sampled downhill potential; orange: storage/overflow required.",
            "Thick: larger contributing area; rings: depression candidates.",
            "Macro samples/corridors only. NO final river beds or filled lakes.",
            "Precipitation, flow, permanence and seasonal regime: UNKNOWN.")):
            draw.text((pad, height-footer+10+row*17), text, fill=(220, 230, 240))
        panel.save(output/f"{name}.png")
    contact = Image.new("RGB", (2*width, height))
    for i, panel in enumerate(panels):
        contact.paste(panel, (i*width, 0))
    contact.save(output/"hydrology.png")


def export_records(plan: HydrologyPlan, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    records = {"network": plan.network_records(), "basins": plan.basin_records(),
               "divides": plan.divide_records(), "closed_basins": plan.closed_basin_records(),
               "depressions": plan.lake_records(), "below_datum_bodies": plan.water_records()}
    (output/"records.json").write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")
