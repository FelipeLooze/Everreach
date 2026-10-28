"""Offline W1 diagnostics: extensive quantities, not player discoveries or lake maps."""
import json
from collections import Counter

from PIL import Image, ImageDraw

from ..formation_plan import indexed_cell
from ..hydrology.geometry import geometry
from ..hydrology.sectors import _face_uv
from ..sphere_topology import CellKey, SurfacePoint
from .balance import STORES
from .query import node_record, regime, regional_sector_record


def metrics(plan):
    h1, periods = plan.hydrology, plan.solution.periods
    domain = [i for i, ocean in enumerate(h1.drainage.marine) if not ocean]
    land = [i for i in domain if h1.heights[i] >= h1.sea_level_m]
    area = sum(h1.cell_area_m2[i] for i in land)
    local = [sum(p["fluxes"]["local_runoff"][i] for p in periods) for i in range(len(h1.heights))]
    total = {key: sum(p["totals"][key] for p in periods) for key in periods[0]["fluxes"]}
    start, end = periods[0]["totals"]["start_storage"], periods[-1]["totals"]["end_storage"]
    residual = start+total["precipitation"]-total["evapotranspiration"]-total["ocean_export"]-end
    types, confirmed = Counter(), []
    for i in h1.channel_index:
        amounts = [p["fluxes"]["outflow"][i] for p in periods]
        if plan.support[i] == "bilateral_downhill_validated":
            label = regime(amounts, plan.year_days, plan.config.flow_presence_liters_per_second)
            types[label] += 1
            if any(amounts):
                confirmed.append(i)
    pools = []
    for pool in h1.drainage.depressions:
        amounts = [sum(period["stores"]["depression"][i] for i in pool) for period in periods]
        pools.append({"h1_candidate_id": h1.identifier("lake-candidate", pool[0]),
            "sum_column_capacity_reference_liters": sum(plan.capacities_liters[i] for i in pool),
            "period_storage_liters": amounts, "positive_storage_periods": sum(v > 0 for v in amounts),
            "connected_pool_capacity_validated": False, "permanent": None, "geometry": None})
    basins, supply_area = {}, Counter()
    for i in domain:
        root = h1.drainage.outlet[i]
        row = basins.setdefault(root, {"h1_potential_catchment_id": h1.identifier("basin", root),
            "precipitation_liters": 0, "actual_et_liters": 0, "local_available_runoff_liters": 0,
            "start_storage_liters": 0, "end_storage_liters": 0, "ocean_export_liters": 0})
        row["precipitation_liters"] += sum(p["fluxes"]["precipitation"][i] for p in periods)
        row["actual_et_liters"] += sum(p["fluxes"]["evapotranspiration"][i] for p in periods)
        row["local_available_runoff_liters"] += local[i]
        row["start_storage_liters"] += sum(values[i] for values in plan.solution.initial_stores)
        row["end_storage_liters"] += sum(periods[-1]["stores"][name][i] for name in STORES)
    for root, row in basins.items():
        row["ocean_export_liters"] = sum(p["fluxes"]["ocean_export"][root] for p in periods)
        row["residual_liters"] = row["start_storage_liters"]+row["precipitation_liters"]-row["actual_et_liters"]-row["ocean_export_liters"]-row["end_storage_liters"]
    for i in land:
        label = regime([p["fluxes"]["local_runoff"][i] for p in periods], plan.year_days, plan.config.flow_presence_liters_per_second)
        supply_area[label] += h1.cell_area_m2[i]
    return {"water_version": 1, "signature": plan.signature, "source_signature": h1.source_signature,
        "hydrology_signature": h1.signature, "climate_signature": plan.climate_signature,
        "radius_m": h1.radius_m, "nodes": len(h1.heights), "climate_version": plan.config.source_climate_version,
        "warmup_years": plan.config.warmup_years, "fixed_evidence_regions": len(plan.manifest),
        "route_status_counts": dict(Counter(plan.support)), "validated_route_regimes": dict(types),
        "model_fed_sampled_edge_count": len(confirmed), "model_fed_nodes": confirmed,
        "land_mean_precipitation_mm": sum(p["fluxes"]["precipitation"][i] for p in periods for i in land)/area if area else None,
        "land_mean_actual_et_mm": sum(p["fluxes"]["evapotranspiration"][i] for p in periods for i in land)/area if area else None,
        "land_mean_pet_mm": sum(p["fluxes"]["pet"][i] for p in periods for i in land)/area if area else None,
        "land_mean_local_runoff_mm": sum(local[i] for i in land)/area if area else None,
        "land_zero_local_runoff_fraction": sum(h1.cell_area_m2[i] for i in land if not local[i])/area if area else None,
        "land_local_supply_regime_area_fractions": {key: value/area for key, value in supply_area.items()} if area else {},
        "year_domain_start_liters": start, "year_domain_end_liters": end, "year_totals_liters": total,
        "year_residual_liters": residual, "period_residual_liters": [p["totals"]["residual_liters"] for p in periods],
        "final_stores_liters": {key: sum(periods[-1]["stores"][key]) for key in STORES},
        "unresolved_is_not_mapped_flooding": True, "permanent_lakes_declared": 0,
        "candidate_storage_groups": pools, "catchment_budgets": list(basins.values())}


def depth_color(value):
    if value <= 0:
        return 91, 65, 48
    f = min(1, value/400)
    return tuple(round(a+(b-a)*f) for a, b in zip((210, 201, 143), (43, 160, 222)))


def write_preview(plan, output, seed=None):
    output.mkdir(parents=True, exist_ok=True)
    h1, g, n = plan.hydrology, geometry(plan.hydrology.config.level), 2**plan.hydrology.config.level
    size, pad, top, width, height = 192, 16, 76, 640, 596
    names = ("annual_runoff", "period_1_runoff", "period_3_runoff", "snow_storage", "column_storage", "pending_accounting", "basins")
    panels = {name: Image.new("RGB", (width, height), (17, 23, 32)) for name in names}
    def origin(face):
        return pad+(face%3)*(size+pad), top+(face//3)*(size+24)
    def pixel(point, face):
        u, v = _face_uv(point, face)
        ox, oy = origin(face)
        return ox+round(float(u+1)*(size-1)/2), oy+round(float(1-v)*(size-1)/2)
    for i, area in enumerate(h1.cell_area_m2):
        key = indexed_cell(i, h1.config.level)
        ox, oy = origin(key.face)
        box = ox+key.x*size//n, oy+(n-1-key.y)*size//n, ox+(key.x+1)*size//n-1, oy+(n-key.y)*size//n-1
        p = plan.solution.periods
        values = {"annual_runoff": sum(period["fluxes"]["local_runoff"][i] for period in p)/area,
            "period_1_runoff": p[1]["fluxes"]["local_runoff"][i]/area,
            "period_3_runoff": p[3]["fluxes"]["local_runoff"][i]/area,
            "snow_storage": p[-1]["stores"]["snow"][i]/area,
            "column_storage": p[-1]["stores"]["depression"][i]/area,
            "pending_accounting": p[-1]["stores"]["unresolved"][i]/area}
        for name, panel in panels.items():
            if h1.drainage.marine[i]:
                color = (18, 45, 76)
            elif name == "basins":
                code = h1.drainage.outlet[i]*2654435761
                color = tuple(50+((code >> shift)&127) for shift in (0, 8, 16))
            else:
                color = depth_color(values[name])
            ImageDraw.Draw(panel).rectangle(box, fill=color)
    for source in h1.channel_index:
        target = h1.drainage.parent[source]
        edge = g.edge_lookup[tuple(sorted((source, target)))]
        fed = any(p["fluxes"]["outflow"][source] for p in plan.solution.periods)
        state = plan.support[source]
        color = (80, 245, 255) if fed else (230, 151, 70) if state == "storage_capacity_unresolved" else (155, 70, 70) if state == "hr1_incompatible" else (85, 88, 92)
        for a, b, face in ((g.points[source], g.ports[edge], indexed_cell(source, h1.config.level).face),
                           (g.ports[edge], g.points[target], indexed_cell(target, h1.config.level).face)):
            for panel in panels.values():
                ImageDraw.Draw(panel).line((pixel(a, face), pixel(b, face)), fill=color, width=2 if fed else 1)
    for name, panel in panels.items():
        draw = ImageDraw.Draw(panel)
        draw.text((pad, 10), f"EVERREACH / W1 / seed {seed} / {name} / OFFLINE", fill="white")
        draw.text((pad, 29), f"R={h1.radius_m/1000:g} km | {len(h1.heights)} nodes | {len(plan.manifest)} fixed HR1 regions", fill=(200, 215, 230))
        for face in range(6):
            x, y = origin(face)
            draw.text((x, y-17), f"Face {face}", fill="white")
        for row, text in enumerate(("Depth: brown zero / sand low / blue >=400 mm (macro quantities).",
            "Cyan: model-fed validated EDGE; grey: pending; orange: storage unknown.",
            "Lines show H1 representatives, not final local river beds. Red: incompatible.",
            "Column stocks and pending accounts are NOT mapped lakes or flooded areas.")):
            draw.text((pad, height-78+row*17), text, fill=(220, 230, 240))
        panel.save(output/f"{name}.png")
    combined = Image.new("RGB", (width*3, height*2))
    for index, name in enumerate(names[:6]):
        combined.paste(panels[name], ((index%3)*width, (index//3)*height))
    combined.save(output/"water.png")


def write_regional_preview(plan, region, output):
    key = CellKey(*region["tile"])
    snapshot = regional_sector_record(plan, key, region)
    panel_width, panel_height, size = 452, 466, 360
    image = Image.new("RGB", (2*panel_width, 2*panel_height), (17, 23, 32))
    draw = ImageDraw.Draw(image)
    area = plan.hydrology.cell_area_m2[region["node"]]
    for season in range(4):
        ox, oy = (season%2)*panel_width+40, (season//2)*panel_height+68
        def pixel(ray):
            u, v = _face_uv(SurfacePoint(*ray), key.face)
            x = (float(u+1)*2**key.level/2-key.x)*size
            y = (float(v+1)*2**key.level/2-key.y)*size
            return round(ox+x), round(oy+size-y)
        draw.rectangle((ox, oy, ox+size, oy+size), outline=(100, 115, 130))
        for piece in snapshot["segments"]:
            amount = piece["period_throughput_liters"][season]
            color = (65, 235, 250) if amount else (110, 115, 125)
            draw.line([pixel(point) for point in piece["points"]], fill=color, width=3 if amount else 1)
        for port in region["ports"]:
            x, y = pixel(port["point"])
            draw.ellipse((x-4, y-4, x+4, y+4), fill=(255, 224, 135))
        x, y = pixel(region["junction"]["point"])
        draw.ellipse((x-4, y-4, x+4, y+4), fill="white")
        period = plan.solution.periods[season]
        rain, runoff = (period["fluxes"][name][region["node"]]/area for name in ("precipitation", "local_runoff"))
        q = period["fluxes"]["outflow"][region["node"]]*4/(plan.year_days*86400*1000)
        draw.text((ox-20, oy-54), f"W1 / region {region['node']} / period {season}", fill="white")
        draw.text((ox-20, oy-35), f"P={rain:.1f} mm | local runoff={runoff:.1f} mm", fill=(220, 230, 240))
        draw.text((ox-20, oy+size+10), f"Outlet mean Q={q:.3g} m3/s | sampled geometry", fill=(220, 230, 240))
        draw.text((ox-20, oy+size+27), "Melt/prior stocks feed Q; cyan=sampled, T1 bed pending.", fill=(190, 205, 220))
    image.save(output/"regional-water.png")
