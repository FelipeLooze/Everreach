"""Compare existing V3/V4 audits, plus bounded multi-seed nucleation statistics."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_v4 import FormationConfigV4, activation_thresholds, RANDOM_RANGE
from app.game.world.genesis.formation_plates import nucleate_plates
from app.game.world.genesis.formation_validation import plate_site_density
from app.game.world.genesis.formation_v4 import nucleate_plates_v4
from app.game.world.genesis.validation_report import case_name


def _paired_sheet(pairs, root, name):
    if not pairs:
        return
    width, height = 0, 0
    frames = []
    for seed, radius in pairs:
        left = root/"v3"/case_name(seed, radius)/"terrain.png"
        right = root/"v4"/case_name(seed, radius)/"terrain.png"
        with Image.open(left) as a, Image.open(right) as b:
            if a.size != b.size:
                raise ValueError("Compare audits at the same diagnostic resolution")
            width, height = a.size
            frame = Image.new("RGB", (2*width, height+20), (17, 23, 32))
            frame.paste(a, (0, 20))
            frame.paste(b, (width, 20))
            draw = ImageDraw.Draw(frame)
            draw.text((8, 4), "V3", fill="white")
            draw.text((width+8, 4), "V4 / spherical-area sites", fill="white")
            frames.append(frame)
    columns = min(3, len(frames))
    sheet = Image.new("RGB", (2*width*columns, (height+20)*((len(frames)+columns-1)//columns)), (17, 23, 32))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (i%columns*2*width, i//columns*(height+20)))
    sheet.save(root/name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Directory with v3/ and v4/ audit outputs")
    parser.add_argument("--density-seeds", type=int, default=512)
    parser.add_argument("--v3-baseline", type=Path, help="Optional previous audit root to verify frozen V3 plans")
    args = parser.parse_args()
    if not 16 <= args.density_seeds <= 4096:
        parser.error("density-seeds must be 16..4096")
    old = json.loads((args.root/"v3/comparison.json").read_text(encoding="utf-8"))
    new = json.loads((args.root/"v4/comparison.json").read_text(encoding="utf-8"))
    by_key = {(c["seed"], c["radius_m"]): c for c in old}
    pairs = []
    table = ["# Formação V3 × V4", "", "Mesmas seeds/raios; área ponderada por ângulo sólido. Contagens são diagnósticas na mesma resolução.", "",
        "| Seed | Raio km | Placas V3 → V4 | Terra % V3 → V4 | Corpos terrestres V3 → V4 | Discordância % V3 → V4 |",
        "| --- | --- | --- | --- | --- | --- |"]
    for case in new:
        key = case["seed"], case["radius_m"]
        before = by_key[key]
        if before["diagnostic_level"] != case["diagnostic_level"]:
            raise ValueError("Mismatched sampling levels")
        pairs.append(key)
        table.append(f"| {key[0]} | {key[1]/1000:g} | {before['plate_count']} → {case['plate_count']} | {before['weighted_land_fraction']*100:.2f} → {case['weighted_land_fraction']*100:.2f} | {before['land_components']} → {case['land_components']} | {before['weighted_macro_disagreement_fraction']*100:.2f} → {case['weighted_macro_disagreement_fraction']*100:.2f} |")
    (args.root/"version-comparison.md").write_text("\n".join(table)+"\n", encoding="utf-8")
    _paired_sheet([key for key in pairs if key[1] == 63_710_000], args.root, "paired-reference.png")
    _paired_sheet([key for key in pairs if key[1] != 63_710_000], args.root, "paired-radii.png")
    if args.v3_baseline:
        checks = []
        for seed, radius in pairs:
            old_path = args.v3_baseline/case_name(seed, radius)/"plan.json"
            new_path = args.root/"v3"/case_name(seed, radius)/"plan.json"
            old_plan = json.loads(old_path.read_text(encoding="utf-8"))
            current = json.loads(new_path.read_text(encoding="utf-8"))
            checks.append({"seed": seed, "radius_m": radius, "identical": old_plan == current,
                           "sha256": hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()})
        (args.root/"v3-compatibility.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        if not all(c["identical"] for c in checks):
            raise ValueError("Frozen V3 plan changed; stop validation")
    statistics = []
    for radius in (6_371_000, 63_710_000, 637_100_000, 1_000_000_000_000):
        row = {"radius_m": radius, "seeds": args.density_seeds, "seed_range": [0, args.density_seeds-1]}
        for version, config_cls, sampler in ((3, FormationConfig, nucleate_plates), (4, FormationConfigV4, nucleate_plates_v4)):
            config = config_cls(radius_m=radius)
            counts = []
            def inventories():
                for seed in range(args.density_seeds):
                    plates = sampler(seed, config)
                    counts.append(len(plates))
                    yield SimpleNamespace(plates=plates)
            result = plate_site_density(inventories())
            result["plate_count"] = {"min": min(counts), "max": max(counts), "mean": sum(counts)/len(counts)}
            row[f"v{version}"] = result
        row["v4_expected_plates_before_structural_minimum"] = sum(activation_thresholds(FormationConfigV4(radius_m=radius)))/RANDOM_RANGE
        statistics.append(row)
        print(json.dumps(row), flush=True)
        (args.root/"density-statistics.json").write_text(json.dumps(statistics, indent=2), encoding="utf-8")
    # Simple diagnostic bar chart; same surface-area normalization for each version.
    image = Image.new("RGB", (980, 380), (17, 23, 32))
    draw = ImageDraw.Draw(image)
    draw.text((16, 10), f"Site density / sphere-area average | {args.density_seeds} seeds per radius | V3 blue / V4 gold", fill="white")
    for i, row in enumerate(statistics):
        origin = 16+i*244
        draw.text((origin, 38), f"R={row['radius_m']/1000:g} km", fill="white")
        for j, zone in enumerate(("center", "edge", "corner")):
            x = origin+20+j*70
            draw.text((x-5, 325), zone, fill="white")
            for version, color, shift in ((3, (60, 160, 220), 0), (4, (235, 193, 83), 24)):
                value = row[f"v{version}"]["site_density_relative_to_surface_average"][zone]
                y = 310-round(value*125)
                draw.rectangle((x+shift, y, x+shift+20, 310), fill=color)
                draw.text((x+shift-1, y-14), f"{value:.2f}", fill=color)
        draw.line((origin, 185, origin+220, 185), fill=(220, 230, 240))
    draw.text((16, 354), "White line = relative density 1. Counts fluctuate; no individual seed is forced to be uniform.", fill=(185, 200, 215))
    image.save(args.root/"density-comparison.png")


if __name__ == "__main__":
    main()
