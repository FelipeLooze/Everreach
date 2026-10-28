"""Technical view of an unmodified real T1 passage and its P1/W2 balances."""
from pathlib import Path
from PIL import Image, ImageDraw
from ...terrain.preview import _font, _raster
from ...terrain.address import TerrainTile, chart
from ...sphere_topology import SurfacePoint


def write_preview(records, summary, sampler, output):
    proof = records["proof"]
    tile = TerrainTile(*proof["allocation"]["tile"])
    n = proof["config"]["grid_intervals"]
    grid = [[sampler.sample(tile.point(x, y, n))["height_mm"] for x in range(n+1)] for y in range(n+1)]
    low, high = min(map(min, grid)), max(map(max, grid))
    image = Image.new("RGB", (1600, 1180), "#111c26")
    draw = ImageDraw.Draw(image)
    font, small = _font(20), _font(17)
    draw.text((20, 12), "EVERREACH / P1 — REAL NATURAL T1 PASSAGE / seed 42", font=_font(26), fill="white")
    draw.text((20, 52), f"Node {summary['source_node']} / {summary['capacity']['length_mm']/1000:.3f} m / no terrain conditioning or incision", font=font, fill="#c4d9e7")
    background = _raster(grid, low, high, proof["config"]["target_spacing_m"]).resize((730, 430))
    for origin, label in (((20, 128), "Before: original T1 authority"), ((820, 128), "After: SAME T1 + modeled water passage")):
        draw.text((origin[0], 96), label, fill="white", font=font)
        image.paste(background, origin)
    def xy(ray, origin):
        _, u, v, d = chart(SurfacePoint(*ray), tile.face)
        return (origin[0]+int((u*2**tile.level/d-tile.x)*729),
                origin[1]+429-int((v*2**tile.level/d-tile.y)*429))
    origin = (820, 128)
    coords = [xy(p, origin) for p in proof["points"]]
    draw.line(coords, fill="#74e5f5", width=6)
    for point, color in ((coords[0], "#ffd07a"), (coords[-1], "#8beeaf")):
        draw.ellipse((point[0]-6, point[1]-6, point[0]+6, point[1]+6), fill=color)
    for section in proof["cross_sections"]:
        draw.line([xy(section["points"][0], origin), xy(section["points"][-1], origin)], fill="#79a8c8", width=2)
    draw.text((20, 576), f"T1 range {low/1000:.3f}..{high/1000:.3f} m — identical pixels, different ledger state", font=small, fill="#c4d9e7")
    draw.text((20, 624), "Longitudinal ground + available model head", font=font, fill="white")
    zs, hs = proof["terrain_profile_mm"], proof["head_profile_reference_mm"]
    lo, hi = min(zs), max(hs)
    for values, color in ((zs, "#dfc17e"), (hs, "#74e5f5")):
        points = [(35+i*165, 844-(z-lo)*175/max(1, hi-lo)) for i, z in enumerate(values)]
        draw.line(points, fill=color, width=3)
    draw.text((20, 870), f"Design depth {proof['capacity']['depth_mm']} mm / five confined sampled sections", font=small, fill="#c4d9e7")
    draw.text((820, 624), "Exact water ledger (litres)", font=font, fill="white")
    entries = [("L1 quota debit from W1 surface", summary["localized_liters"]),
               ("Source before / after", f"{summary['source_before_liters']} / {summary['source_after_liters']}"),
               ("Receiver before / after", f"{summary['receiver_before_liters']} / {summary['receiver_after_liters']}"),
               ("Retained to wet the reach", summary["retained_in_reach_liters"]),
               ("Delivered downstream", summary["delivered_liters"]),
               ("Parent / child residual", f"{summary['parent_residual_liters']} / {summary['child_residual_liters']}")]
    for i, (label, value) in enumerate(entries):
        draw.text((820, 670+i*34), f"{label}: {value}", font=small, fill="#8beeaf" if i >= 4 else "#c4d9e7")
    cap = proof["capacity"]
    draw.text((20, 930), f"K1 estimate: {cap['q_mm3_s']/1e6:.6f} L/s; episode cap {cap['episode_capacity_liters']} L; roughness n={cap['roughness_n_milli']/1000:g}", font=font, fill="white")
    draw.text((20, 966), "Model uses integer Manning, 10% capacity factor, limited velocity, wetting reserve and receiver containment.", font=small, fill="#c6d7e2")
    draw.text((20, 1002), "This is a short episodic proof, NOT a perennial river, a connected continental network or an ocean outlet.", font=small, fill="#ddbc89")
    draw.text((20, 1038), "L1 uniform surface-film allocation is explicit new-model localization; unknown W1 water stays unlocalized.", font=small, fill="#ddbc89")
    draw.text((20, 1074), "Source + receiver + reach = same total before/after. Child balances are a breakdown of W2, never extra water.", font=small, fill="#ddbc89")
    draw.text((20, 1110), "New seasonal C2 inputs require the F1 future-event/local-balance contract; no historical rain is credited twice.", font=small, fill="#ddbc89")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    image.save(output/"practical-passage.png")
