"""Deterministic TP1 great-circle route diagnostic (raw selector opportunities only)."""
import json
from pathlib import Path
from app.game.world.genesis.local_formations import candidate, candidate_v2
from app.game.world.genesis.sphere_config import SphereConfig
from app.game.world.genesis.sphere_topology import CellKey, cell_center, neighbor
from app.game.world.genesis.sphere_metric import distance_m

SEEDS=(42,0,7,2026,12345)
RADII=(31_855_000,63_710_000,127_420_000)
TARGETS_KM=(5,20,50,100,500)

def trace(seed,radius):
    config=SphereConfig(radius_m=radius,sector_level=10)
    cell=CellKey(face=seed%6,level=17,x=65_536,y=65_536+(seed%17))
    seen={cell};km=0.0;points=[]
    previous_point=cell_center(cell);stride=0
    while km<TARGETS_KM[-1]:
        nxt=neighbor(cell,"east")
        if nxt in seen:raise RuntimeError("Local TP1 route unexpectedly looped")
        current_point=cell_center(nxt);km+=distance_m(config,previous_point,current_point)/1000
        points.append((km,vars(nxt).copy()));seen.add(nxt);cell=nxt;previous_point=current_point
    return points,0,0,round(km,2)

def summarize(seed,points,faces,stride,route_km,selector):
    found=[];counts={target:{"cells":0,"candidates":0,"types":{}} for target in TARGETS_KM}
    for km,address in points:
        archetype=selector(seed,address)
        if archetype:found.append((km,archetype))
        for target in TARGETS_KM:
            if km<=target:
                counts[target]["cells"]+=1
                counts[target]["candidates"]+=int(archetype is not None)
                if archetype:counts[target]["types"][archetype]=counts[target]["types"].get(archetype,0)+1
    intervals=[round(found[i][0]-found[i-1][0],2) for i in range(1,len(found))]
    return {"cells":len(points),"face_transitions":faces,"candidate_count":len(found),"route_km":route_km,"stride_m":stride,
        "candidate_types":{k:sum(v==k for _,v in found) for k in sorted({v for _,v in found})},
        "spacing_km":{"min":min(intervals) if intervals else None,"median":sorted(intervals)[len(intervals)//2] if intervals else None,
                      "max":max(intervals) if intervals else None},
        "distance_buckets":{str(k):v for k,v in counts.items()}}

def main():
    result={"method":"500 km walk along exact adjacent TP1 east-neighbor cells, measured by spherical cell-center distance; no barrier/E1 checks; raw candidates only. Seam continuity is covered by topology regression tests.",
        "targets_km":list(TARGETS_KM),"results":[]}
    for radius in RADII:
        for seed in SEEDS:
            points,faces,stride,route_km=trace(seed,radius)
            result["results"].append({"seed":seed,"radius_m":radius,
                "v1":summarize(seed,points,faces,stride,route_km,candidate),
                "v2_raw_pre_context":summarize(seed,points,faces,stride,route_km,candidate_v2)})
    path=Path(__file__).resolve().parents[1]/"wgs1_route_density.json"
    path.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2));print("artifact:",path)
if __name__=="__main__":main()
