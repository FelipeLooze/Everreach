"""Limited natural-T1 proof before any terrain-authority change or water debit."""
import json
from pathlib import Path
from scripts.preview_water import sources
from app.game.world.genesis.water.plan import load_water_plan
from app.game.world.genesis.terrain.field import build_terrain_plan, TerrainSampler
from app.game.world.genesis.water_reconciliation.practical.config import PracticalConfig
from app.game.world.genesis.water_reconciliation.practical.proof import select_candidates


def main():
    source, h1, climate = sources(42, 63_710_000)
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root/"artifacts/water-w1/seed-42-r63710000/plan.json").read_text())
    water = load_water_plan(data, h1, climate, data["hr_signature"])
    found, trials = select_candidates(water, TerrainSampler(build_terrain_plan(source)), PracticalConfig())
    output = root/"artifacts/practical-hydrology-p1"
    output.mkdir(parents=True, exist_ok=True)
    (output/"probe.json").write_text(json.dumps({"found": found, "trials": trials}, indent=2), encoding="utf-8")
    print(json.dumps({"found": found is not None, "trials": len(trials), "last": trials[-1] if trials else None,
        "capacity": found["capacity"] if found else None, "transfer_liters": found["suggested_transfer_liters"] if found else 0}))


if __name__ == "__main__":
    main()
