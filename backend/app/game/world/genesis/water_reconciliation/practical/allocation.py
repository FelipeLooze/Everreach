"""L1 conservative fixed-leaf surface-film quotas. No unknown-water relocation."""
from .. import ledger
from ...terrain.address import TerrainTile, level_for_spacing
from ...hydro_geometry.spatial import vertex_areas_mm2


def parcel_level(radius, config):
    return level_for_spacing(radius, config.target_spacing_m, config.grid_intervals)


def split_integer(total, weights):
    denominator = sum(weights)
    if type(total) is not int or total < 0 or not denominator or any(type(w) is not int or w < 0 for w in weights):
        raise ValueError("L1 needs nonnegative integral quantities and positive area")
    output, cumulative, previous = [], 0, 0
    for weight in weights:
        cumulative += weight
        current = total*cumulative//denominator
        output.append(current-previous)
        previous = current
    return output


def surface_quota(water, tile, config):
    if tile.level != parcel_level(water.hydrology.radius_m, config) or tile.level < water.hydrology.config.level:
        raise ValueError("L1 claims only one fixed leaf resolution; parent/child duplication is forbidden")
    from ...formation_plan import cell_index
    from ...sphere_topology import CellKey
    parent = tile.parent(water.hydrology.config.level)
    node = cell_index(CellKey(*vars(parent).values()))
    amount = water.solution.periods[-1]["stores"]["surface"][node]
    current = parent
    while current.level < tile.level:
        children = [TerrainTile(current.face, current.level+1, current.x*2+dx, current.y*2+dy)
                    for dy in range(2) for dx in range(2)]
        weights = [sum(vertex_areas_mm2(c, 4, water.hydrology.radius_m)) for c in children]
        allocated = split_integer(amount, weights)
        ancestor = tile.parent(current.level+1)
        index = children.index(ancestor)
        current, amount = ancestor, allocated[index]
    areas = vertex_areas_mm2(tile, config.grid_intervals, water.hydrology.radius_m)
    shares = split_integer(amount, areas)
    return {"version": 1, "source_node": node, "source_account": "w1:surface", "tile": list(vars(tile).values()),
            "parcel_quota_liters": amount, "vertex_areas_mm2": areas, "vertex_quota_liters": shares,
            "area_policy": "hierarchical_integer_spherical_quadrature_uniform_surface_film",
            "unresolved_water_localized": False}
