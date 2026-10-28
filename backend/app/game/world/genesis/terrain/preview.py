"""Offline technical comparisons; no player map or runtime renderer."""
from pathlib import Path
from math import sqrt
from PIL import Image, ImageDraw, ImageFont
from ..formation_tectonics import evaluate
from .address import level_for_spacing, tile_at
from .patch import prepare_patch


def _font(size):
    for name in ("C:/Windows/Fonts/consola.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _raster(grid, minimum, maximum, spacing):
    n = len(grid)
    im = Image.new("RGB", (n, n))
    for y in range(n):
        for x in range(n):
            value = grid[y][x]
            t = (value-minimum)/max(1, maximum-minimum)
            dx = (grid[y][min(n-1, x+1)]-grid[y][max(0, x-1)])/max(1, spacing*2000)
            dy = (grid[min(n-1, y+1)][x]-grid[max(0, y-1)][x])/max(1, spacing*2000)
            light = max(.22, min(1.15, (.7-.4*dx-.4*dy)/sqrt(1+dx*dx+dy*dy)))
            rgb = (60+160*t, 110+85*t, 120-50*t)
            im.putpixel((x, n-1-y), tuple(max(0, min(255, int(c*light))) for c in rgb))
    return im.resize((368, 326), Image.Resampling.BILINEAR)


def write_comparison(sampler, point, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 1460), "#101a23")
    draw = ImageDraw.Draw(image)
    font, small = _font(19), _font(16)
    source = sampler.plan.source
    draw.text((20, 12), f"EVERREACH / T1   seed {source.seed}   R={source.config.radius_m:,} m", fill="white", font=_font(26))
    draw.text((20, 49), "Same full-spectrum authority at every LOD. Per-row shared elevation scale; symmetric relief shading.", fill="#b4c4d4", font=small)
    records = []
    for row, (label, spacing) in enumerate((("MACRO", 5000), ("REGIONAL", 250), ("LOCAL", 2))):
        tile = tile_at(point, level_for_spacing(source.config.radius_m, spacing, sampler.plan.config.sample_intervals))
        patch = prepare_patch(sampler, tile)
        n = sampler.plan.config.sample_intervals
        samples = [[sampler.sample(tile.point(x, y, n)) for x in range(n+1)] for y in range(n+1)]
        raw = [[evaluate(source.seed, source.config, source.plates, tile.point(x, y, n), causes=False)["elevation_m"]*1000
                for x in range(n+1)] for y in range(n+1)]
        base = patch["base_mm"]
        regional = [[p["base_v4_reconstructed_mm"]+p["regional_detail_mm"] for p in line] for line in samples]
        full = patch["height_mm"]
        grids = raw, base, regional, full
        low, high = min(v for grid in grids for line in grid for v in line), max(v for grid in grids for line in grid for v in line)
        y = 90+row*435
        draw.text((20, y), f"{label}: tile L{tile.level} / spacing <= {patch['max_sample_spacing_m_upper_bound']} m / {low/1000:.2f}..{high/1000:.2f} m", fill="white", font=font)
        for col, (title, grid) in enumerate(zip(("V4 original (integer m)", "T1 reconstructed base", "T1 regional morphology", "T1 full local field"), grids)):
            x = 20+col*395
            draw.text((x, y+28), title, fill="#d1e4ed", font=small)
            image.paste(_raster(grid, low, high, patch["max_sample_spacing_m_upper_bound"]), (x, y+56))
        errors = [abs(a-b) for ra, rb in zip(raw, base) for a, b in zip(ra, rb)]
        detail = [v for line in patch["detail_mm"] for v in line]
        records.append({"scale": label, "tile": list(vars(tile).values()),
            "sample_count": (n+1)**2, "sample_spacing_upper_m": patch["max_sample_spacing_m_upper_bound"],
            "base_v4_max_error_mm": max(errors), "base_v4_mean_abs_error_mm": sum(errors)/len(errors),
            "height_range_mm": [min(v for line in full for v in line), max(v for line in full for v in line)],
            "detail_range_mm": [min(detail), max(detail)]})
        draw.text((20, y+389), f"Base vs V4 max error {max(errors)/1000:.3f} m; added detail {min(detail)/1000:.3f}..{max(detail)/1000:.3f} m", fill="#b4c4d4", font=small)
    draw.text((20, 1410), "Technical witness, not land-coverage statistics. Interpolated pixels are NOT authoritative heights.", fill="#d3b78b", font=small)
    draw.text((20, 1435), "No river incision, lake permanence, material assignment or player-visible coordinates.", fill="#d3b78b", font=small)
    image.save(output/"terrain-comparison.png")
    return records
