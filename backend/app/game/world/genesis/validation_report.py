"""Comparison images and tabular developer reports from already sampled grids."""
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw

from .formation_plan import FormationPlan, load_plan
from .formation_config import FormationConfig
from .sphere_config import parse_config
from .formation_preview import terrain_color
from .formation_validation import DiagnosticGrid, plate_site_density


def case_name(seed: int, radius_m: int) -> str:
    return f"seed-{seed}_r-{radius_m}"


def write_case(plan: FormationPlan, grid: DiagnosticGrid, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    n, pad, header = 2**grid.level, 8, 42
    size = (3*(n+pad)+pad, header+2*(n+20)+42)
    layers = {name: Image.new("RGB", size, (17, 23, 32)) for name in ("terrain", "connectivity", "uplift")}
    for face in range(6):
        x0, y0 = pad+face%3*(n+pad), header+face//3*(n+20)
        for layer in layers.values():
            ImageDraw.Draw(layer).text((x0, y0-14), ("+X", "-X", "+Y", "-Y", "+Z", "-Z")[face], fill="white")
        for y in range(n):
            for x in range(n):
                i = face*n*n+y*n+x
                position = x0+x, y0+n-1-y
                z, t, label = grid.heights[i], grid.tectonic[i], grid.labels[i]
                layers["terrain"].putpixel(position, terrain_color(z, plan.config.sea_level_m))
                value = (label+1)*2654435761
                color = tuple(70+((value >> shift)&127) for shift in (0, 8, 16))
                if z < plan.config.sea_level_m:
                    color = color[0]//3, color[1]//2, color[2]
                layers["connectivity"].putpixel(position, (255, 245, 50) if grid.macro_mismatch[i] else color)
                magnitude = min(1, abs(t)/2000)
                color = ((int(30+220*magnitude), 35, 40) if t >= 0 else (25, 65, int(45+205*magnitude)))
                layers["uplift"].putpixel(position, color)
    for name, layer in layers.items():
        draw = ImageDraw.Draw(layer)
        draw.text((pad, 6), f"Seed {plan.seed} | R {plan.config.radius_m/1000:g} km", fill="white")
        draw.text((pad, 20), f"V{plan.config.generator_version} / {name} / diagnostic L{grid.level}", fill=(180, 195, 210))
        draw.text((pad, size[1]-36), f"Area land {grid.summary['weighted_land_fraction']:.1%} | macro diff {grid.summary['weighted_macro_disagreement_fraction']:.1%}", fill="white")
        draw.text((pad, size[1]-21), f"Bodies L/W {grid.summary['land_components']}/{grid.summary['water_components']} | DEV ONLY", fill=(180, 195, 210))
        layer.save(directory/f"{name}.png")
    (directory/"metrics.json").write_text(json.dumps(grid.summary, indent=2), encoding="utf-8")
    (directory/"plan.json").write_text(json.dumps(plan.to_dict(), separators=(",", ":")), encoding="utf-8")


def write_comparison(cases: list[dict], directory: Path, reference_radius: int = 63_710_000) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory/"comparison.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    fields = ["seed", "radius_m", "weighted_land_fraction", "unweighted_land_fraction",
        "weighted_macro_disagreement_fraction", "land_components", "water_components",
        "macro_land_components", "macro_water_components", "largest_land_share_of_land",
        "longest_land_extent_lower_bound_km", "longest_uplift_belt_lower_bound_km",
        "small_land_components_le_4_cells", "plate_count", "plan_seconds", "sampling_seconds", "analysis_seconds"]
    with (directory/"comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(cases)
    version = cases[0]["config"]["generator_version"] if cases else "?"
    table = [f"# Comparação geográfica v{version}", "", "Área ponderada pelo ângulo sólido de cada célula; conectividade diagnóstica na resolução amostrada.", "",
             "| Seed | Raio km | Terra % | Sem peso % | Discordância % | Corpos T/A | Maior terra / terra % | Extensão terra km ≥ | Faixa elevada km ≥ | p05 / p50 / p95 m |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for case in cases:
        h = case["elevation_m"]
        table.append(f"| {case['seed']} | {case['radius_m']/1000:g} | {100*case['weighted_land_fraction']:.2f} | {100*case['unweighted_land_fraction']:.2f} | {100*case['weighted_macro_disagreement_fraction']:.2f} | {case['land_components']}/{case['water_components']} | {100*case['largest_land_share_of_land']:.1f} | {case['longest_land_extent_lower_bound_km']:.0f} | {case['longest_uplift_belt_lower_bound_km']:.0f} | {h['p05']} / {h['p50']} / {h['p95']} |")
    (directory/"comparison.md").write_text("\n".join(table)+"\n", encoding="utf-8")
    reference_plans = []
    for case in cases:
        if case["radius_m"] == reference_radius:
            data = json.loads((directory/case_name(case["seed"], case["radius_m"])/"plan.json").read_text(encoding="utf-8"))
            reference_plans.append(load_plan(data, case["seed"], parse_config(data["config"])))
    if reference_plans:
        (directory/"site-density.json").write_text(json.dumps(plate_site_density(reference_plans), indent=2), encoding="utf-8")
    for group, selected in (("reference", [c for c in cases if c["radius_m"] == reference_radius]),
                             ("radii", [c for c in cases if c["radius_m"] != reference_radius])):
        if not selected:
            continue
        for layer in ("terrain", "connectivity", "uplift"):
            pictures = [Image.open(directory/case_name(c["seed"], c["radius_m"])/f"{layer}.png") for c in selected]
            w, h = pictures[0].size
            columns = min(5, len(pictures))
            sheet = Image.new("RGB", (columns*w, ((len(pictures)+columns-1)//columns)*h), (17, 23, 32))
            for i, picture in enumerate(pictures):
                sheet.paste(picture, ((i%columns)*w, (i//columns)*h))
                picture.close()
            sheet.save(directory/f"{group}-{layer}.png")
