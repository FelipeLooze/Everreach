"""Optional water audit; compartment stocks never become local habitat proofs."""
from app.db.models.world_water import GenesisWaterPlan
from app.db.models.world_water_reconciliation import GenesisWaterReconciliation,GenesisWaterDomain
from app.db.models.world_practical_hydrology import GenesisPracticalHydrology
from ..water.service import get_water_plan
from ..formation_plan import cell_index
from ..sphere_topology import cell_at


def audit_water_context(db,campaign_id,point):
    water=db.get(GenesisWaterPlan,campaign_id)
    result={"W1_present":water is not None,"W2_present":db.get(GenesisWaterReconciliation,campaign_id) is not None,
        "P1_present":db.get(GenesisPracticalHydrology,campaign_id) is not None,
        "local_permanent_water_confirmed":None,"vegetation_evidence":None,
        "policy":"macro_stocks_and_episodic_passage_do_not_confirm_river_lake_saturation_or_vegetation"}
    if water is not None:
        plan=get_water_plan(db,campaign_id)
        node=cell_index(cell_at(point,plan.hydrology.config.level))
        result.update(W1_signature=plan.signature,W1_node=node,
            W1_final_macro_surface_liters=plan.solution.periods[-1]["stores"]["surface"][node],
            W1_spatial_stock_location="not_a_local_wetness_footprint")
        domain=db.get(GenesisWaterDomain,(campaign_id,node))
        result["W2_local_head_present"]=domain is not None
    return result
