"""F1 future-forcing proposal contract; no atmospheric water is credited here."""
from ...terrain.field import checksum
from ...terrain.address import TerrainTile
from ...formation_plan import cell_index
from ...sphere_topology import CellKey
from ...hydro_geometry.spatial import vertex_areas_mm2
from .allocation import split_integer, parcel_level


def _leaf_share(total, tile, macro_level, radius):
    current = tile.parent(macro_level)
    while current.level < tile.level:
        children = [TerrainTile(current.face, current.level+1, current.x*2+x, current.y*2+y)
                    for y in range(2) for x in range(2)]
        weights = [sum(vertex_areas_mm2(c, 4, radius)) for c in children]
        next_cell = tile.parent(current.level+1)
        total = split_integer(total, weights)[children.index(next_cell)]
        current = next_cell
    return total


def future_forcing_proposal(water, tile, config, *, cutover_minute, cycle, period):
    if (any(type(v) is not int for v in (cutover_minute, cycle, period)) or cutover_minute < 0 or
            cycle < 0 or period not in range(4) or tile.level != parcel_level(water.hydrology.radius_m, config)):
        raise ValueError("F1 requires a future cycle, one of four periods, and the fixed L1 leaf")
    h1 = water.hydrology
    parent = tile.parent(h1.config.level)
    node = cell_index(CellKey(*vars(parent).values()))
    macro_area = h1.cell_area_m2[node]
    snow = water.snowfall_mm[period][node]*macro_area
    rain = (water.precipitation_mm[period][node]-water.snowfall_mm[period][node])*macro_area
    demand = water.pet_mm[period][node]*macro_area
    arguments = tile, h1.config.level, h1.radius_m
    leaf_snow, leaf_rain, leaf_pet = (_leaf_share(v, *arguments) for v in (snow, rain, demand))
    ordinal = cycle*4+period
    quarter_minutes = water.year_days*360
    data = {"kind": "future_forcing_proposal_f1", "forcing_version": 1, "cycle": cycle, "period": period,
        "interval_start_minute": cutover_minute+ordinal*quarter_minutes,
        "interval_end_minute": cutover_minute+(ordinal+1)*quarter_minutes,
        "w1_climate_source_signature": water.climate_signature, "tile": list(vars(tile).values()),
        "snowfall_liters": leaf_snow, "rainfall_liters": leaf_rain, "precipitation_liters": leaf_rain+leaf_snow,
        "pet_demand_liters": leaf_pet, "historical_W1_flux_recredited": False,
        "origin": "new_logical_interval_after_checkpoint_not_historical_W1_period_replay",
        "credit_authorized": False,
        "required_before_application": ["unique_interval_receipt", "sequential_previous_period", "localized_soil_and_snow_state",
            "bounded_ET_infiltration_melt_balance", "explicit_external_input_in_W2_ledger"]}
    if water.config.source_climate_version==3:
        data.update(climate_version=3,climate_forcing_contract=water.config.forcing_contract,
            atmospheric_recycling_credit=False,PET_semantics='total_potential_demand_not_net_of_atmospheric_return')
    data["proposal_id"] = checksum(["F1", config.model_dump(), cutover_minute, data])[:32]
    return data
