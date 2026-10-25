"""Run from backend: python -m scripts.preview_planet --seed 42 --output ../artifacts/planet-v3"""
import argparse
from pathlib import Path
import json

from app.game.world.genesis.formation_config import FormationConfig
from app.game.world.genesis.formation_plan import build_plan, load_plan
from app.game.world.genesis.formation_preview import write_preview
from app.game.world.genesis.formation_geography import sample_at
from app.game.world.genesis.sphere_topology import SurfacePoint


def main():
    parser = argparse.ArgumentParser(description="Offline v3 developer planet atlas; never opens a game save")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--radius-m", type=int, default=63_710_000)
    parser.add_argument("--face-size", type=int, default=96)
    parser.add_argument("--output", type=Path, help="Directory for the atlas, summary and reproducible plan")
    parser.add_argument("--plan", type=Path, help="Optional exported GenesisWorld.plan JSON, read-only")
    parser.add_argument("--inspect-ray", type=int, nargs=3, metavar=("X", "Y", "Z"),
                        help="Print elevation, physical identity and geological causes for an integer ray")
    args = parser.parse_args()
    if not 16 <= args.face_size <= 256:
        parser.error("face-size must be 16..256")
    if args.output is None and args.inspect_ray is None:
        parser.error("Provide --output and/or --inspect-ray")
    if args.plan:
        data = json.loads(args.plan.read_text(encoding="utf-8"))
        config = FormationConfig.model_validate(data["config"])
        plan = load_plan(data, data["seed"], config)
    else:
        plan = build_plan(args.seed, FormationConfig(radius_m=args.radius_m))
    if args.output:
        print(json.dumps(write_preview(plan, args.output, args.face_size), indent=2))
    if args.inspect_ray is not None:
        print(json.dumps(sample_at(plan, SurfacePoint(*args.inspect_ray)), indent=2))


if __name__ == "__main__":
    main()
