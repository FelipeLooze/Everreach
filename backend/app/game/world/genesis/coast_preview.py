"""Read-only local coast atlas, with shared ports and subordinate fragments."""
import json
from pathlib import Path

from PIL import Image, ImageDraw

from .coast_refinement import build_coast_patch, _between
from .formation_plan import FormationPlan, indexed_cell
from .formation_tectonics import evaluate
from .sphere_topology import CellKey, DIRECTIONS, cell_at, cell_center, neighbor


def choose_coast_tile(plan: FormationPlan, tile_level: int) -> CellKey:
    """Deterministic baseline shore selection for the offline example/benchmark only."""
    for index in range(len(plan.labels)):
        key = indexed_cell(index, plan.config.macro_level)
        a = cell_center(key)
        a_land = plan.component_at(a).kind == "landmass"
        for direction in DIRECTIONS:
            b = cell_center(neighbor(key, direction))
            if (plan.component_at(b).kind == "landmass") == a_land:
                continue
            lo, hi, denominator = 0, 2**20, 2**20
            while hi-lo > 1:
                mid = (lo+hi)//2
                height = evaluate(plan.seed, plan.config, plan.plates, _between(a, b, mid, denominator), causes=False)["elevation_m"]
                if (height >= plan.config.sea_level_m) == a_land:
                    lo = mid
                else:
                    hi = mid
            return cell_at(_between(a, b, (lo+hi)//2, denominator), tile_level)
    raise ValueError("No macro shore in this plan; no coast example was forced")


def write_coast_preview(plan: FormationPlan, patch: dict, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    tile = CellKey(*patch["tile"])
    factor = 2**(patch["detail_level"]-tile.level)
    pixel, pad, header = max(6, 320//factor), 12, 68
    face_span = factor*pixel
    image = Image.new("RGB", (2*face_span+3*pad, face_span+header+65), (17, 23, 32))
    draw = ImageDraw.Draw(image)
    draw.text((pad, 8), f"V{plan.config.generator_version} COAST R1 | seed {plan.seed} | R={plan.config.radius_m/1000:g} km | fixed patch", fill="white")
    draw.text((pad, 24), f"tile={patch['tile']} detail=L{patch['detail_level']} | baseline only, sampled continuity", fill=(180, 195, 210))
    draw.text((pad, 47), "Old macro classification", fill="white")
    draw.text((face_span+2*pad, 47), f"Subordinate local fragments (same v{plan.config.generator_version} height)", fill="white")
    sampled_macro_mismatches = 0
    for ordinal, fragment in enumerate(patch["fragments"]):
        value = (ordinal+1)*2654435761
        color = tuple(70+((value >> shift)&127) for shift in (0, 8, 16))
        if fragment["kind"] == "water":
            color = color[0]//3, color[1]//2, color[2]
        for values in fragment["cells"]:
            key = CellKey(*values)
            x, y = key.x-tile.x*factor, key.y-tile.y*factor
            macro_land = plan.component_at(cell_center(key)).kind == "landmass"
            sampled_macro_mismatches += macro_land != (fragment["kind"] == "land")
            for origin, cell_color in ((pad, (184, 180, 115) if macro_land else (22, 77, 145)),
                                        (face_span+2*pad, color)):
                left, top = origin+x*pixel, header+(factor-1-y)*pixel
                draw.rectangle((left, top, left+pixel-1, top+pixel-1), fill=cell_color)
    draw.text((pad, header+face_span+12), f"fragments={len(patch['fragments'])} | ports={len(patch['ports'])} | shore brackets={len(patch['shore_brackets'])}", fill="white")
    draw.text((pad, header+face_span+29), f"samples={patch['sample_count']} | macro/local different cells={sampled_macro_mismatches}/{patch['interior_cells']}", fill=(180, 195, 210))
    draw.text((pad, header+face_span+46), "Colors are local IDs. Open fragments do not prove a closed global island or navigable route.", fill=(180, 195, 210))
    image.save(output/"coast.png")
    (output/"patch.json").write_text(json.dumps(patch, indent=2), encoding="utf-8")
    result = {"tile": patch["tile"], "detail_level": patch["detail_level"],
              "fragments": len(patch["fragments"]), "macro_local_different_cells": sampled_macro_mismatches,
              "sample_count": patch["sample_count"]}
    (output/"summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
