"""Run from backend: python -m scripts.preview_planet --seed 42 --output ../artifacts/planet-v3"""
import argparse
from pathlib import Path
import json

from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.sphere_config import parse_config
from app.game.world.genesis.formation_plan import build_plan, load_plan
from app.game.world.genesis.formation_preview import write_preview
from app.game.world.genesis.formation_geography import sample_at
from app.game.world.genesis.sphere_topology import SurfacePoint
from app.game.world.genesis.sphere_topology import CellKey
from app.game.world.genesis.coast_refinement import build_coast_patch
from app.game.world.genesis.coast_preview import choose_coast_tile, write_coast_preview


def main():
    parser = argparse.ArgumentParser(description="Offline V3/V4 developer planet atlas; never opens a game save")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--radius-m", type=int, default=63_710_000)
    parser.add_argument("--formation-version", type=int, choices=(3, 4), default=3)
    parser.add_argument("--face-size", type=int, default=96)
    parser.add_argument("--output", type=Path, help="Directory for the atlas, summary and reproducible plan")
    parser.add_argument("--plan", type=Path, help="Optional exported GenesisWorld.plan JSON, read-only")
    parser.add_argument("--inspect-ray", type=int, nargs=3, metavar=("X", "Y", "Z"),
                        help="Print elevation, physical identity and geological causes for an integer ray")
    parser.add_argument("--coast-level", type=int, choices=range(2, 25),
                        help="Render a bounded local R1 coast patch instead of the full atlas")
    parser.add_argument("--coast-tile", type=int, nargs=4, metavar=("FACE", "LEVEL", "X", "Y"),
                        help="Optional fixed patch tile; default selects a deterministic baseline shore")
    args = parser.parse_args()
    if not 16 <= args.face_size <= 256:
        parser.error("face-size must be 16..256")
    if args.output is None and args.inspect_ray is None:
        parser.error("Provide --output and/or --inspect-ray")
    if args.coast_tile is not None and args.coast_level is None:
        parser.error("--coast-tile requires --coast-level")
    if args.coast_level is not None and args.output is None:
        parser.error("--coast-level requires --output")
    if args.plan:
        data = json.loads(args.plan.read_text(encoding="utf-8"))
        config = parse_config(data["config"])
        if not isinstance(config, FormationConfig):
            parser.error("This formation viewer supports only V3/V4 plans")
        plan = load_plan(data, data["seed"], config)
    else:
        config_class = FormationConfigV4 if args.formation_version == 4 else FormationConfig
        plan = build_plan(args.seed, config_class(radius_m=args.radius_m))
    if args.output:
        if args.coast_level is not None:
            tile = CellKey(*args.coast_tile) if args.coast_tile else choose_coast_tile(
                plan, max(plan.config.macro_level, args.coast_level-5))
            patch = build_coast_patch(plan, tile, args.coast_level)
            print(json.dumps(write_coast_preview(plan, patch, args.output), indent=2))
        else:
            print(json.dumps(write_preview(plan, args.output, args.face_size), indent=2))
    if args.inspect_ray is not None:
        print(json.dumps(sample_at(plan, SurfacePoint(*args.inspect_ray)), indent=2))


if __name__ == "__main__":
    main()
