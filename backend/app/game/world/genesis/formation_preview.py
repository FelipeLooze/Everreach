"""Offline developer atlas. No game routes, database writes or discovery changes."""
from pathlib import Path
import json
import time

from PIL import Image, ImageDraw

from .formation_geography import sample_at
from .formation_plan import FormationPlan, indexed_cell
from .sphere_topology import face_point

FACE_NAMES = ("+X", "-X", "+Y", "-Y", "+Z (north)", "-Z (south)")


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(x+(y-x)*t) for x, y in zip(a, b))


def terrain_color(height: int, sea: int) -> tuple[int, int, int]:
    height -= sea
    if height < 0:
        return _mix((7, 24, 67), (58, 156, 178), (height+8000)/8000)
    if height < 2000:
        return _mix((181, 191, 121), (169, 128, 78), height/2000)
    return _mix((169, 128, 78), (250, 247, 239), (height-2000)/7000)


def write_preview(plan: FormationPlan, output: Path, face_size: int = 96) -> dict:
    if type(face_size) is not int or not 16 <= face_size <= 256:
        raise ValueError("Developer preview face size must be 16..256")
    output.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    pad, header, footer = 12, 52, 54
    width = 3*(face_size+pad)+pad
    height = 2*(face_size+28)+header+footer
    panels = {name: Image.new("RGB", (width, height), (17, 23, 32))
              for name in ("terrain", "components", "tectonics")}
    minimum, maximum, local_land, mismatch = 10**9, -10**9, 0, 0
    dominant = {}
    mechanisms = {}
    for face in range(6):
        origin = (pad+(face%3)*(face_size+pad), header+(face//3)*(face_size+28))
        for name, panel in panels.items():
            ImageDraw.Draw(panel).text((origin[0], origin[1]-17), f"Face {face}: {FACE_NAMES[face]}", fill=(235, 238, 243))
        for y in range(face_size):
            for x in range(face_size):
                p = face_point(face, 2*x+1, 2*y+1, 2*face_size)
                sample = sample_at(plan, p)
                z = sample["elevation_m"]
                minimum, maximum = min(minimum, z), max(maximum, z)
                local_land += z >= plan.config.sea_level_m
                mismatch += sample["identity"]["resolution_mismatch"]
                pixel = (origin[0]+x, origin[1]+face_size-1-y)
                panels["terrain"].putpixel(pixel, terrain_color(z, plan.config.sea_level_m))
                component = plan.component_at(p)
                color_key = int(component.id.split(":")[1][:8], 16) ^ component.anchor_index*2654435761
                color = tuple(65+((color_key >> shift)&127) for shift in (0, 8, 16))
                if component.kind == "water_body":
                    color = (color[0]//3, color[1]//2, color[2])
                panels["components"].putpixel(pixel, (255, 245, 50) if sample["identity"]["resolution_mismatch"] else color)
                slot = sample["dominant_plate"]
                dominant[(face, x, y)] = slot
                mechanism = max(sample["structures"], key=lambda s: abs(s["contribution_m"]), default=None)
                if mechanism:
                    kind = mechanism["mechanism"]
                    mechanisms[kind] = mechanisms.get(kind, 0)+1
                    color = ((225, 95, 70) if "collision" in kind or "arc" in kind else
                             (70, 187, 213) if "rift" in kind or "ridge" in kind else (190, 150, 220))
                    color = _mix((27, 33, 44), color, min(1, abs(sample["terms_m"]["tectonic"])/1500))
                else:
                    color = (27, 33, 44)
                panels["tectonics"].putpixel(pixel, color)
    # Thin internal plate edges are developer annotations, never game barriers.
    for (face, x, y), slot in dominant.items():
        if any(dominant.get((face, nx, ny), slot) != slot for nx, ny in ((x+1, y), (x, y+1))):
            origin = (pad+(face%3)*(face_size+pad), header+(face//3)*(face_size+28))
            panels["tectonics"].putpixel((origin[0]+x, origin[1]+face_size-1-y), (240, 221, 160))
    summary = {"seed": plan.seed, "generator_version": 3, "signature": plan.signature,
               "config": plan.config.model_dump(mode="json"), "scale": plan.to_dict()["scale"],
               "plate_count": len(plan.plates), "landmass_count_macro": sum(c.kind == "landmass" for c in plan.components),
               "water_body_count_macro": sum(c.kind == "water_body" for c in plan.components),
               "height_range_m": [minimum, maximum], "preview_land_fraction": local_land/(6*face_size**2),
               "macro_disagreement_fraction": mismatch/(6*face_size**2), "sampled_mechanisms": mechanisms,
               "face_size": face_size, "elapsed_seconds": round(time.perf_counter()-start, 3)}
    captions = {"terrain": "Elevation: deep blue < 0 m; sand lowlands; brown/white high relief.",
                "components": "MACRO identities. Yellow = local land/water differs from macro cell.",
                "tectonics": "Red: convergence; cyan: divergence. Gold: plate edges (not barriers)."}
    for name, panel in panels.items():
        draw = ImageDraw.Draw(panel)
        draw.text((pad, 8), f"EVERREACH / FORMATION V3 / {name.upper()} / seed {plan.seed}", fill=(245, 247, 250))
        draw.text((pad, 23), f"R={plan.config.radius_m/1000:g} km | plates={len(plan.plates)} | OFFLINE DEV ONLY", fill=(170, 185, 203))
        # Two short lines fit even in compact contact sheets.
        caption = captions[name]
        midpoint = caption.rfind(" ", 0, 65)
        draw.text((pad, height-42), caption[:midpoint], fill=(200, 212, 225))
        draw.text((pad, height-27), caption[midpoint+1:], fill=(200, 212, 225))
        panel.save(output/f"{name}.png")
    contact = Image.new("RGB", (width*3, height), (17, 23, 32))
    for i, panel in enumerate(panels.values()):
        contact.paste(panel, (width*i, 0))
    contact.save(output/"planet.png")
    (output/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output/"plan.json").write_text(json.dumps(plan.to_dict(), separators=(",", ":")), encoding="utf-8")
    return summary
