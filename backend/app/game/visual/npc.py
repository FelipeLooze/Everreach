"""Phase 21E — NPC Visual Identity.

NPC (app.db.models.npc) carries zero appearance data today — unlike
items (21D), where quality/material/condition already existed
elsewhere in Canon, an NPC's stable/current visual traits genuinely
belong in app.game.visual.spec's VisualIdentity table; there is
nothing to derive them from instead.

WHICH stable/current keys an NPC's traits dict uses is deliberately
NOT validated or enumerated here (spec's own field list is explicitly
"potential fields, only where useful" — hair_color/eye_color/
permanent_scars/... are examples, never a required schema). A caller
sets whatever it has established as Canon; nothing here invents
biometric detail nobody asked for.

resolve_npc_appearance is the one inheritance case this subphase
builds: REGIONAL tendency + the NPC's own stable identity + the NPC's
own current state, composed with app.game.visual.spec's shared
resolve_visual_layers (later layers win, explicit Canon overrides a
broad regional default — spec's own guard-uniform example). Culture/
Organization/Profession layers are real, later additions once 21I
(Regional Visual Identity) and 21J (Organization Heraldry) exist to
actually populate something at those layers — adding empty/unused
layers now would be exactly the "uncontrolled style-resolution engine"
the spec warns against.
"""
from sqlalchemy.orm import Session

from app.db.models.npc import NPC
from app.game.visual.spec import (
    VisualSpec,
    get_visual_spec,
    resolve_visual_layers,
    set_current_visual_state,
    set_stable_visual_traits,
)


class NPCVisualIdentityError(ValueError):
    pass


def set_npc_stable_identity(
    db: Session, campaign_id: str, npc_id: str, traits: dict
) -> VisualSpec:
    return set_stable_visual_traits(db, "npc", npc_id, traits, campaign_id=campaign_id)


def set_npc_current_appearance(
    db: Session, campaign_id: str, npc_id: str, state: dict
) -> VisualSpec:
    return set_current_visual_state(db, "npc", npc_id, state, campaign_id=campaign_id)


def get_npc_visual_spec(db: Session, campaign_id: str, npc_id: str) -> VisualSpec:
    return get_visual_spec(db, "npc", npc_id, campaign_id=campaign_id)


def resolve_npc_appearance(db: Session, campaign_id: str, npc_id: str) -> dict:
    """Regional tendency, then this NPC's own stable identity, then
    their current state — each layer only overrides what it actually
    has an opinion about (resolve_visual_layers skips None values)."""
    npc = db.get(NPC, npc_id)
    if npc is None:
        raise NPCVisualIdentityError(f"NPC {npc_id} does not exist.")

    regional = get_visual_spec(db, "region", npc.region_id, campaign_id=campaign_id).stable
    personal = get_visual_spec(db, "npc", npc_id, campaign_id=campaign_id)

    return resolve_visual_layers(regional, personal.stable, personal.current)
