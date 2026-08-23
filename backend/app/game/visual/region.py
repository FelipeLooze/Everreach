"""Phase 21I — Regional Visual Identity.

Every earlier subphase (21E NPC, 21G Location, 21H Settlement) already
reads a Region's/Subregion's visual traits through
app.game.visual.spec's generic get_visual_spec(db, "region", ...) /
"subregion" — the plumbing already existed. This subphase's own,
additive contribution is: named, discoverable accessors (instead of
every caller having to remember the raw "region"/"subregion" subject_
kind strings) and resolve_subregion_visual, the one real inheritance
case this level needs — a Subregion's own Canon overriding its
Region's broader tendency (spec: "Vale Verdejante may broadly share
cultural architecture while Gray Mountains / Fields of Cardal / Great
Lake Country look meaningfully different" — REGIONAL IDENTITY +
SUBREGIONAL VARIATION, not one flat Region-wide constant).

Regional identity provides TENDENCIES, never absolute per-location
rules (spec, mandatory) — nothing here forces every Location inside a
Region to inherit these traits; app.game.visual.location.
resolve_location_visual already only USES this as the broadest,
lowest-priority layer, always overridable by anything more specific.
"""
from sqlalchemy.orm import Session

from app.db.models.subregion import Subregion
from app.game.visual.spec import (
    VisualSpec,
    get_visual_spec,
    resolve_visual_layers,
    set_current_visual_state,
    set_stable_visual_traits,
)


class RegionalVisualIdentityError(ValueError):
    pass


def set_region_visual_identity(db: Session, campaign_id: str, region_id: str, traits: dict) -> VisualSpec:
    return set_stable_visual_traits(db, "region", region_id, traits, campaign_id=campaign_id)


def get_region_visual_spec(db: Session, campaign_id: str, region_id: str) -> VisualSpec:
    return get_visual_spec(db, "region", region_id, campaign_id=campaign_id)


def set_subregion_visual_identity(db: Session, campaign_id: str, subregion_id: str, traits: dict) -> VisualSpec:
    return set_stable_visual_traits(db, "subregion", subregion_id, traits, campaign_id=campaign_id)


def set_subregion_current_state(db: Session, campaign_id: str, subregion_id: str, state: dict) -> VisualSpec:
    return set_current_visual_state(db, "subregion", subregion_id, state, campaign_id=campaign_id)


def get_subregion_visual_spec(db: Session, campaign_id: str, subregion_id: str) -> VisualSpec:
    return get_visual_spec(db, "subregion", subregion_id, campaign_id=campaign_id)


def resolve_subregion_visual(db: Session, campaign_id: str, subregion_id: str) -> dict:
    subregion = db.get(Subregion, subregion_id)
    if subregion is None:
        raise RegionalVisualIdentityError(f"Subregion {subregion_id} does not exist.")

    region_layer = get_region_visual_spec(db, campaign_id, subregion.region_id).stable
    subregion_spec = get_subregion_visual_spec(db, campaign_id, subregion_id)

    return resolve_visual_layers(region_layer, subregion_spec.stable, subregion_spec.current)
