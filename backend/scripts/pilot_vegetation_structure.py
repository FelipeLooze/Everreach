"""Sparse planetary examples, not global biome quotas or area prevalence."""
from collections import Counter
import argparse,json
from scripts.validate_vegetation import inputs_vg1
from scripts.calibrate_vegetation import OUT
from app.game.world.genesis.vegetation.v2 import VegetationSamplerV2
from app.game.world.genesis.sphere_topology import cell_center,CellKey


def run(seed):
    source=inputs_vg1(seed);sampler=VegetationSamplerV2(source.environment,source.water)
    counts=Counter();examples={}
    for face in range(6):
        for y in range(8):
            for x in range(8):
                sample=sampler.sample(cell_center(CellKey(face,3,x,y)))
                counts[sample["physiognomy"]]+=1;examples.setdefault(sample["physiognomy"],sample)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/f"global-structure-pilot-{seed}.json").write_text(json.dumps({"counts":dict(counts),"examples":examples},indent=2),encoding="utf-8")
    print(json.dumps({"seed":seed,"counts":dict(counts)}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--seeds",type=int,nargs="+",default=[42]);args=p.parse_args()
    for seed in args.seeds:run(seed)
