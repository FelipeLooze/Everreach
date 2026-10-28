import json
from .address import TerrainTile


def prepare_patch(sampler, tile):
    if not isinstance(tile, TerrainTile):
        raise ValueError("T1 needs an explicit TerrainTile")
    plan, config = sampler.plan, sampler.plan.config
    n = config.sample_intervals
    if (n+1)**2 > config.max_patch_samples:
        raise ValueError("T1 sample budget exceeded before generation")
    if 2*plan.source.config.radius_m > config.max_patch_span_m*2**tile.level:
        raise ValueError("T1 patch span budget exceeded; request smaller tiles")
    records = [[sampler.sample(tile.point(x, y, n)) for x in range(n+1)] for y in range(n+1)]
    data = {"kind": "terrain_patch_t1", "terrain_version": 1, "signature": plan.signature,
            "tile": [tile.face, tile.level, tile.x, tile.y], "sample_intervals": n,
            "height_mm": [[p["height_mm"] for p in row] for row in records],
            "base_mm": [[p["base_v4_reconstructed_mm"] for p in row] for row in records],
            "detail_mm": [[p["detail_mm"] for p in row] for row in records],
            "max_sample_spacing_m_upper_bound": (2*plan.source.config.radius_m+n*2**tile.level-1)//(n*2**tile.level),
            "physical_sector": list(vars(tile.physical_ancestor(plan.source.config.sector_level)).values())
                if tile.level >= plan.source.config.sector_level else None,
            "interpolation_authoritative": False, "modifications_applied": False}
    if len(json.dumps(data, separators=(",", ":")).encode()) > config.max_patch_bytes:
        raise ValueError("T1 persistence budget exceeded; no patch saved")
    validate_patch(plan, tile, data)
    return data


def validate_patch(plan, tile, data):
    n = plan.config.sample_intervals
    if (data.get("kind") != "terrain_patch_t1" or type(data.get("terrain_version")) is not int or
            data["terrain_version"] != 1 or data.get("signature") != plan.signature or
            data.get("tile") != list(vars(tile).values()) or data.get("sample_intervals") != n):
        raise ValueError("T1 patch version/address/source mismatch; refusing regeneration")
    for field in ("height_mm", "base_mm", "detail_mm"):
        grid = data.get(field)
        if (not isinstance(grid, list) or len(grid) != n+1 or any(not isinstance(row, list) or len(row) != n+1 or
                any(type(v) is not int for v in row) for row in grid)):
            raise ValueError("Invalid T1 persisted grid")
    if any(data["height_mm"][y][x] != data["base_mm"][y][x]+data["detail_mm"][y][x]
           for y in range(n+1) for x in range(n+1)):
        raise ValueError("T1 height terms disagree")


def saved_sample(data, tile, point):
    from .address import chart
    face, u, v, d = chart(point, tile.face)
    if d <= 0:
        return None
    n = data["sample_intervals"]
    a, b = u*2**tile.level*n-tile.x*n*d, v*2**tile.level*n-tile.y*n*d
    if a%d or b%d or not 0 <= a//d <= n or not 0 <= b//d <= n:
        return None
    x, y = a//d, b//d
    return {"height_mm": data["height_mm"][y][x], "base_v4_reconstructed_mm": data["base_mm"][y][x],
            "detail_mm": data["detail_mm"][y][x]}
