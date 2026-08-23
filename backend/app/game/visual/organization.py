"""Phase 21J — Organization Heraldry & Symbol Identity.

Reuses Phase 13's Organization data in full — no emblem/heraldry
column exists on Organization (audited), so app.game.visual.spec's
VisualIdentity table (subject_kind="organization") is the legitimate,
sole store for it, the same pattern 21E (NPC) already established for
an entity with no prior appearance data of its own.

"SYMBOLS MUST BE CANON... do not casually regenerate a completely
different emblem later" (spec, mandatory) is enforced the same
structural way stable traits always are here: set_organization_
heraldry MERGES into whatever heraldry already exists, it never
silently replaces the whole thing — updating "official_colors" cannot
accidentally erase an already-established "emblem_description".

suggest_heraldry_formality is the one derived helper this subphase
adds: a read-only hint, from REAL Canon
(Organization.organization_type/formality/visibility), for whoever is
about to establish a new organization's heraldry — "match formality to
organization" (spec: a Kingdom warrants formal heraldry, a small
hunter group a simple badge, a CRIMINAL/PRIVATE organization a hidden
mark). It never sets or invents an emblem itself — only Canon-driven
guidance for a human/game-designer decision, exactly like the rest of
this module never fabricates gameplay truth.
"""
from sqlalchemy.orm import Session

from app.core.enums import OrganizationFormality, OrganizationType, OrganizationVisibility
from app.db.models.organization import Organization
from app.game.visual.spec import (
    VisualSpec,
    get_visual_spec,
    set_current_visual_state,
    set_stable_visual_traits,
)

_FORMAL_HERALDRY_TYPES = frozenset({
    OrganizationType.POLITICAL, OrganizationType.MILITARY, OrganizationType.RELIGIOUS,
})


class OrganizationVisualIdentityError(ValueError):
    pass


def set_organization_heraldry(db: Session, campaign_id: str, organization_id: str, traits: dict) -> VisualSpec:
    return set_stable_visual_traits(db, "organization", organization_id, traits, campaign_id=campaign_id)


def set_organization_current_display(
    db: Session, campaign_id: str, organization_id: str, state: dict
) -> VisualSpec:
    return set_current_visual_state(db, "organization", organization_id, state, campaign_id=campaign_id)


def get_organization_visual_spec(db: Session, campaign_id: str, organization_id: str) -> VisualSpec:
    return get_visual_spec(db, "organization", organization_id, campaign_id=campaign_id)


def suggest_heraldry_formality(db: Session, organization_id: str) -> str:
    """Advisory only — never invents or sets an emblem. One of
    "formal_heraldry" / "trade_mark" / "simple_badge" / "hidden_mark",
    derived from real Canon rather than a fixed lookup table alone."""
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise OrganizationVisualIdentityError(f"Organization {organization_id} does not exist.")

    if organization.visibility == OrganizationVisibility.PRIVATE.value:
        return "hidden_mark"
    if organization.organization_type == OrganizationType.CRIMINAL.value:
        return "hidden_mark"
    if organization.organization_type == OrganizationType.COMMERCIAL.value:
        return "trade_mark"
    if (
        organization.formality == OrganizationFormality.FORMALLY_RECOGNIZED.value
        and organization.organization_type in {member.value for member in _FORMAL_HERALDRY_TYPES}
    ):
        return "formal_heraldry"
    return "simple_badge"
