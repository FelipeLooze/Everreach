"""Phase 21G — Location Visual Identity.

LOCATION BASE IDENTITY vs CURRENT SCENE STATE is the spec's own split
(a stone/wood workshop near the square, vs night + rain + forge
active) — mapped directly onto app.game.visual.spec's stable/current
columns, no new concept invented.

resolve_location_visual composes REGION + SUBREGION (broad tendency,
21I's eventual job to populate — this subphase only wires the seam)
with this Location's own stable identity and current scene state.
Settlement-specific identity (scale, economy-driven materials) is
21H's own, separate layer, added on top of this same resolver rather
than duplicated into it — a Settlement already overlays a Location
(app.db.models.settlement.Settlement.location_id), so 21H's resolver
can call this one and layer its own settlement-kind traits after it.
"""
from sqlalchemy.orm import Session

from app.db.models.location import Location
from app.game.visual.spec import (
    VisualSpec,
    get_visual_spec,
    resolve_visual_layers,
    set_current_visual_state,
    set_stable_visual_traits,
)


class LocationVisualIdentityError(ValueError):
    pass


def set_location_stable_identity(db: Session, campaign_id: str, location_id: str, traits: dict) -> VisualSpec:
    return set_stable_visual_traits(db, "location", location_id, traits, campaign_id=campaign_id)


def set_location_current_scene(db: Session, campaign_id: str, location_id: str, state: dict) -> VisualSpec:
    return set_current_visual_state(db, "location", location_id, state, campaign_id=campaign_id)


def get_location_visual_spec(db: Session, campaign_id: str, location_id: str) -> VisualSpec:
    return get_visual_spec(db, "location", location_id, campaign_id=campaign_id)


def resolve_location_visual(db: Session, campaign_id: str, location_id: str) -> dict:
    location = db.get(Location, location_id)
    if location is None:
        raise LocationVisualIdentityError(f"Location {location_id} does not exist.")

    region_layer = get_visual_spec(db, "region", location.region_id, campaign_id=campaign_id).stable
    subregion_layer = (
        get_visual_spec(db, "subregion", location.subregion_id, campaign_id=campaign_id).stable
        if location.subregion_id is not None
        else {}
    )
    personal = get_visual_spec(db, "location", location_id, campaign_id=campaign_id)

    return resolve_visual_layers(region_layer, subregion_layer, personal.stable, personal.current)
