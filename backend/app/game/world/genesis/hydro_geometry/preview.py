"""Offline technical G1 evidence views. Never a player map."""
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw
from ..terrain.address import TerrainTile, chart
from ..sphere_topology import SurfacePoint
from ..terrain.preview import _font, _raster

COLORS = {"verified_at_requested_resolution": "#6cec99", "pending_resolution": "#ffd16b",
          "partially_verified_storage_required": "#f08b55", "incompatible_fixed_boundary_head": "#ff5687",
          "incompatible_sampled_path_reference_head": "#ff5687", "pending_budget": "#a4adb7"}


def metrics(data):
    return {"status": data["status"], "route_status_counts": dict(Counter(r["status"] for r in data["routes"])),
        "route_geometric_conditions": dict(Counter(r.get("geometric_condition", "unresolved") for r in data["routes"])),
        "route_count": len(data["routes"]), "segment_count": len(data["segments"]), "confluences": len(data["confluences"]),
        "max_sampled_uphill_mm": max([r.get("sampled_uphill_mm", 0) for r in data["routes"]] or [0]),
        "max_probe_spacing_mm": max([r.get("max_probe_spacing_mm", 0) for r in data["routes"]] or [0]),
        "sampled_depression_fragments": len(data["depression_geometry"]["depressions"]),
        "sampled_banked_sections": sum(bool(s["stage_geometry"]) for s in data["sections"]),
        "section_count": len(data["sections"]), "coastal_disagreements": data["coast"]["legacy_t1_disagreements"] if data["coast"] else None,
        "budget": data["budget"], "water_occupation_modeled": False}


def write_preview(data, output, *, region=None, legacy_audit=None, title="G1 local geometry"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 1240), "#101a23")
    draw = ImageDraw.Draw(image)
    font, small = _font(20), _font(16)
    draw.text((20, 15), f"EVERREACH / {title}", fill="white", font=_font(26))
    draw.text((20, 53), f"G1 {data['request_id']} / {data['status']} / T1 heights in mm", fill="#b6c9d8", font=small)
    tile, n = TerrainTile(*data["request"]["tile"]), data["request"]["grid_intervals"]
    origins = [(20, 112), (820, 112), (20, 664)]
    graph = data["graph"]
    if graph:
        grid = [graph["heights_mm"][y*(n+1):(y+1)*(n+1)] for y in range(n+1)]
        low, high = min(map(min, grid)), max(map(max, grid))
        background = _raster(grid, low, high, max(1, data["grid_spacing_upper_bound_m"])).resize((740, 380))
    else:
        low = high = 0
        background = Image.new("RGB", (740, 380), "#27323d")
    def xy(point, origin):
        _, u, v, d = chart(SurfacePoint(*point), tile.face)
        a, b = u*2**tile.level/d-tile.x, v*2**tile.level/d-tile.y
        return origin[0]+int(a*739), origin[1]+379-int(b*379)
    for index, (origin, label) in enumerate(zip(origins, ("Historical H1/HR1 reference on T1", "G1 paths over T1 (colors = proof status)", "Potential depression geometry / spill edges"))):
        draw.text((origin[0], origin[1]-28), label, fill="white", font=font)
        image.paste(background, origin)
        if index == 0 and region:
            for port in region["ports"]:
                draw.line([xy(region["junction"]["point"], origin), xy(port["point"], origin)], fill="#6a9ec9", width=2)
            for segment in region["segments"]:
                draw.line([xy(p, origin) for p in segment["points"]], fill="#ff5f77", width=4)
        if index == 1 and graph:
            lookup = {s["id"]: s for s in data["segments"]}
            for route in data["routes"]:
                for sid in route["segment_ids"]:
                    draw.line([xy(p, origin) for p in lookup[sid]["points"]], fill=COLORS.get(route["status"], "white"), width=4)
            for anchor in data["request"]["anchors"]:
                x, y = xy(anchor["point"], origin)
                draw.ellipse((x-5, y-5, x+5, y+5), fill="#f4f8fc" if anchor["role"] == "outlet" else "#59d3df")
            for junction in data["confluences"]:
                x, y = xy(junction["point"], origin)
                draw.ellipse((x-5, y-5, x+5, y+5), outline="#a581ff", width=3)
        if index == 2 and graph:
            for basin in data["depression_geometry"]["depressions"]:
                for point in basin["footprint_vertices"]:
                    x, y = xy(point, origin)
                    draw.ellipse((x-3, y-3, x+3, y+3), fill="#72bde7")
                for a, b in basin["spill_edges"]:
                    draw.line([xy(graph["points"][a], origin), xy(graph["points"][b], origin)], fill="#bdec93", width=3)
        draw.rectangle((*origin, origin[0]+740, origin[1]+380), outline="#647d8e")
    summary = metrics(data)
    draw.text((20, 508), f"T1 grid range {low/1000:.3f}..{high/1000:.3f} m / tile L{tile.level} / {n} intervals", fill="#bdcbd5", font=small)
    if legacy_audit:
        excess = max([r["max_head_exceedance_mm"] for r in legacy_audit["segments"]] or [0])
        draw.text((20, 532), f"Old HR1 head excess on T1: {excess/1000:.3f} m (NOT resolved by G1)", fill="#ff8c9d", font=small)
    y = 560 if legacy_audit else 535
    for status, count in summary["route_status_counts"].items():
        draw.text((20, y), f"{count} x {status}", fill=COLORS.get(status, "white"), font=small)
        y += 22
    draw.text((820, 508), "Shared point does not prove a complete bilateral route.", fill="#bdcbd5", font=small)
    draw.text((820, 532), f"Largest T1 uphill probe: {summary['max_sampled_uphill_mm']/1000:.3f} m", fill="#bdcbd5", font=small)
    draw.text((820, 556), f"Largest longitudinal probe gap: {summary['max_probe_spacing_mm']/1000:.1f} m", fill="#bdcbd5", font=small)
    draw.text((820, 636), "Sampled transverse section (no actual water level)", fill="white", font=font)
    section = next((s for s in data["sections"] if s["stage_geometry"]), next(iter(data["sections"]), None))
    if section:
        zs = section["terrain_profile_mm"]
        z0, z1 = min(zs), max(zs)
        coords = [(850+i*660/(len(zs)-1), 990-(z-z0)*260/max(1, z1-z0)) for i, z in enumerate(zs)]
        draw.line(coords, fill="#e6ce83", width=4)
        draw.text((830, 682), f"{z0/1000:.3f}..{z1/1000:.3f} m / probes {section['probe_step_mm']/1000:g} m apart", fill="#bdcbd5", font=small)
        draw.text((830, 1020), section["status"], fill="#bdcbd5", font=small)
        draw.text((830, 1043), f"{len(section['stage_geometry'])} potential stage/area pairs; Q capacity unknown", fill="#bdcbd5", font=small)
    else:
        draw.text((830, 720), "Section pending / insufficient budget", fill="#bdcbd5", font=small)
    draw.text((20, 1080), f"{summary['sampled_depression_fragments']} sampled depression fragments; these are NOT lakes.", fill="#bdcbd5", font=small)
    draw.text((20, 1110), f"Samples {data['budget']['sample_count']}/{data['budget']['sample_limit']} / sections {summary['section_count']} / confluences {summary['confluences']}", fill="#bdcbd5", font=small)
    draw.text((20, 1150), "Red: old HR1 reference. Yellow: resolution pending. Green: verified at requested probes. Orange: storage needed.", fill="#d1b48a", font=small)
    draw.text((20, 1180), "Interpolated background is diagnostic; no incision, no water allocation, no active river or permanent lake.", fill="#d1b48a", font=small)
    draw.text((20, 1210), "G1 does not validate all subgrid passages or hydraulic conveyance. W2 reconciliation is separate.", fill="#d1b48a", font=small)
    image.save(output/"geometry.png")
    return summary
