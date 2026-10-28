"""Additional real planets. Coarse C3 diagnostic level, same R1-55 physics/parameters."""
import json,time
from app.game.world.genesis.climate.v3 import ClimateConfigV3R1
from app.game.world.genesis.climate.plan import build_climate_plan
from app.game.world.genesis.environment.adapter import EnvironmentSampler
from app.game.world.genesis.environment.config import EnvironmentConfigC3
from app.game.world.genesis.water.config import WaterConfigC3R155
from app.game.world.genesis.water.plan import build_water_plan
from app.game.world.genesis.vegetation.field import VegetationSampler
from app.game.world.genesis.vegetation.config import VegetationConfig
from app.game.world.genesis.sphere_topology import CellKey,cell_center
from scripts.validate_environment import environment_inputs
from scripts.validate_vegetation import OUT,summarize


def main():
    rows=[]
    for radius in (6371000,254840000,1000000000000):
        start=time.perf_counter();old=environment_inputs(42,radius)
        source=old.regional.terrain.plan.source
        climate=build_climate_plan(source,old.h1,ClimateConfigV3R1(level=3,land_recycling_ppm=550000))
        environment=EnvironmentSampler(old.regional,old.h1,climate,EnvironmentConfigC3())
        water=build_water_plan(source,old.h1,climate,config=WaterConfigC3R155())
        vg=VegetationSampler(environment,water,VegetationConfig(policy="exploration_mosaic_v1"))
        prep=time.perf_counter()-start;start=time.perf_counter()
        samples=[vg.sample(cell_center(CellKey(face,2,x,y))) for face in range(6) for y in range(4) for x in range(4)]
        rows.append({"radius_m":radius,"seed":42,"climate_level":3,"macro_hydrology_level":old.h1.config.level,
            "climate_config":climate.config.model_dump(),"physical_patch_level":vg.level,
            "preparation_seconds":prep,"sampling_seconds":time.perf_counter()-start,
            "vegetation_signature":vg.signature,"water_signature":water.signature,
            "limits":"96 probes; coarser atmospheric resolution than the five reference planets; not a climate quality comparison",
            **summarize(samples)})
        print(json.dumps(rows[-1]),flush=True)
    (OUT/"additional-radii.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")


if __name__=="__main__":main()
