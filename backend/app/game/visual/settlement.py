"""Phase 21H — Settlement Visual Identity.

"Do not represent Arven as six buildings... settlement scale should
communicate different scale" (spec, mandatory) is enforced by always
including a scale layer derived from real Canon —
Settlement.settlement_type (Phase 15F: MAJOR_CITY/CITY/TOWN/VILLAGE/
HAMLET) and population_tier — never left to chance or to whatever a
caller happens to remember to set. A settlement's visual resolution is
its underlying Location's own chain (Region + Subregion + Location,
app.game.visual.location.resolve_location_visual) with this mandatory
scale layer, then any settlement-specific stable/current notes, layered
on top — a Settlement already overlays one Location 1:1
(app.db.models.settlement.Settlement.location_id), so there is no
second, parallel geography here, only an additional visual layer.
"""
from sqlalchemy.orm import Session

from app.db.models.settlement import Settlement
from app.game.visual.location import resolve_location_visual
from app.game.visual.spec import (
    VisualSpec,
    get_visual_spec,
    resolve_visual_layers,
    set_current_visual_state,
    set_stable_visual_traits,
)


class SettlementVisualIdentityError(ValueError):
    pass


def set_settlement_stable_identity(db: Session, campaign_id: str, settlement_id: str, traits: dict) -> VisualSpec:
    return set_stable_visual_traits(db, "settlement", settlement_id, traits, campaign_id=campaign_id)


def set_settlement_current_scene(db: Session, campaign_id: str, settlement_id: str, state: dict) -> VisualSpec:
    return set_current_visual_state(db, "settlement", settlement_id, state, campaign_id=campaign_id)


def get_settlement_visual_spec(db: Session, campaign_id: str, settlement_id: str) -> VisualSpec:
    return get_visual_spec(db, "settlement", settlement_id, campaign_id=campaign_id)


def resolve_settlement_visual(db: Session, campaign_id: str, settlement_id: str) -> dict:
    settlement = db.get(Settlement, settlement_id)
    if settlement is None:
        raise SettlementVisualIdentityError(f"Settlement {settlement_id} does not exist.")

    location_layer = resolve_location_visual(db, campaign_id, settlement.location_id)
    scale_layer = {
        "settlement_scale": settlement.settlement_type,
        "population_tier": settlement.population_tier,
    }
    personal = get_visual_spec(db, "settlement", settlement_id, campaign_id=campaign_id)

    return resolve_visual_layers(location_layer, scale_layer, personal.stable, personal.current)
