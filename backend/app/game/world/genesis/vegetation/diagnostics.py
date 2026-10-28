"""Technical visual structure. Species identity is not a biome or landscape class."""
from collections import Counter


def structure(sample):
    pops=sample["populations"];cover=sample["cover_ppm"]
    return {"form":sample["physiognomy"],"cover_ppm":cover,"density_per_ha":sample["density_per_ha"],
        "canopy_ppm":sample["strata_cover_ppm"]["canopy"],"shrub_ppm":sample["strata_cover_ppm"]["shrub"],
        "ground_ppm":sample["strata_cover_ppm"]["ground"],
        "mean_height_cm":sum(p["height_cm"]*p["cover_ppm"] for p in pops)//max(1,cover),
        "max_height_cm":max((p["height_cm"] for p in pops),default=0)}


def visual_change(a,b):
    a,b=structure(a),structure(b)
    return (a["form"]!=b["form"] or abs(a["cover_ppm"]-b["cover_ppm"])>=100000 or
        abs(a["canopy_ppm"]-b["canopy_ppm"])>=100000 or
        abs(a["mean_height_cm"]-b["mean_height_cm"])>=max(150,min(a["mean_height_cm"],b["mean_height_cm"])//3) or
        max(a["density_per_ha"],b["density_per_ha"])>2*max(100,min(a["density_per_ha"],b["density_per_ha"])))


def route_diagnostics(samples,length_m):
    pairs=list(zip(samples,samples[1:]));swaps=[(a,b) for a,b in pairs if a["dominant_species"]!=b["dominant_species"]]
    return {"samples":len(samples),"length_km":length_m/1000,"step_m":length_m//max(1,len(pairs)),
        "dominant_changes":len(swaps),"form_changes":sum(a["physiognomy"]!=b["physiognomy"] for a,b in pairs),
        "structural_changes":sum(visual_change(a,b) for a,b in pairs),
        "identity_only_changes":sum(not visual_change(a,b) for a,b in swaps),
        "forms":dict(Counter(s["physiognomy"] for s in samples)),
        "cover_ppm_range":[min(s["cover_ppm"] for s in samples),max(s["cover_ppm"] for s in samples)],
        "canopy_ppm_range":[min(s["strata_cover_ppm"]["canopy"] for s in samples),max(s["strata_cover_ppm"]["canopy"] for s in samples)],
        "mean_height_cm_range":[min(structure(s)["mean_height_cm"] for s in samples),max(structure(s)["mean_height_cm"] for s in samples)],
        "sampling_limit":"thresholded_structure_diagnostics_not_a_rendering_or_exact_transition_census"}


def components(grid,key):
    seen=set();sizes=[];n=len(grid)
    for y in range(n):
        for x in range(len(grid[y])):
            if (x,y) in seen:continue
            label=grid[y][x][key];stack=[(x,y)];seen.add((x,y));size=0
            while stack:
                i,j=stack.pop();size+=1
                for u,v in ((i-1,j),(i+1,j),(i,j-1),(i,j+1)):
                    if 0<=v<n and 0<=u<len(grid[v]) and (u,v) not in seen and grid[v][u][key]==label:
                        seen.add((u,v));stack.append((u,v))
            sizes.append(size)
    return {"components":len(sizes),"largest_component_samples":max(sizes,default=0),
        "largest_component_fraction":max(sizes,default=0)/max(1,sum(sizes)),"grid_adjacency":"four_neighbors_sampled_not_exact_geographic_area"}
