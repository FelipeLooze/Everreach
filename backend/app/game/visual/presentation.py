"""Phase 21O — Visual Presentation Contracts.

Frontend-facing DTOs translating resolved visual identity into
something a screen can render — a dataclass, this codebase's own
established DTO pattern (mirrors app.game.map.view.MapViewLocation and
every other Phase 20 view model), per "do not necessarily create
separate classes if current architecture has a cleaner DTO/view-model
pattern" (spec).

Item's own presentation contract is NOT duplicated here: extending it
would mean inventing a second, parallel item response shape when
InventoryItemResponse (app/schemas/inventory.py) already exists and
already carries quality/condition/material/weapon-family — this
subphase only added the one missing field
(signature_ornamentation) directly to that existing schema (see
app/api/routes/inventory.py) instead of building a whole separate
contract nobody would consume ("do not create duplicate appearance
systems", spec, mandatory).

KNOWLEDGE-AWARE VISUAL PRESENTATION (spec, mandatory): build_location_
presentation is the one contract here that genuinely needs a knowledge
gate, and it reuses Phase 20's own gate (app.game.map.view.get_map_view)
rather than re-deriving one — returning None (never partial/fabricated
data) for a location the character's own Map View does not include at
all. NPC and Organization presentations do not gate on Knowledge here:
physical appearance is, by the spec's own example, directly observable
("Logan sees an unknown heraldic banner... show visual emblem, not
automatically the organization name") — what IS knowledge-gated is
identity/semantic information (names, secrets), which these
presentation contracts never claim to resolve; a caller combining this
with a name must apply that gate itself, at the point it reads a name
from Canon.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models.npc import NPC
from app.db.models.organization import Organization
from app.game.map.view import get_map_view
from app.game.visual.location import resolve_location_visual
from app.game.visual.npc import resolve_npc_appearance
from app.game.visual.organization import get_organization_visual_spec
from app.game.visual.spec import resolve_visual_layers


class VisualPresentationError(ValueError):
    pass


@dataclass(frozen=True)
class NPCPresentation:
    npc_id: str
    display_name: str
    icon_category: str = "npc"
    visual_traits: dict = field(default_factory=dict)
    has_visual_detail: bool = False


@dataclass(frozen=True)
class LocationPresentation:
    location_id: str
    display_name: str | None
    icon_category: str
    visual_traits: dict = field(default_factory=dict)
    has_visual_detail: bool = False


@dataclass(frozen=True)
class OrganizationPresentation:
    organization_id: str
    display_name: str
    icon_category: str
    visual_traits: dict = field(default_factory=dict)
    has_visual_detail: bool = False


def build_npc_presentation(db: Session, campaign_id: str, npc_id: str) -> NPCPresentation:
    npc = db.get(NPC, npc_id)
    if npc is None:
        raise VisualPresentationError(f"NPC {npc_id} does not exist.")

    visual_traits = resolve_npc_appearance(db, campaign_id, npc_id)
    return NPCPresentation(
        npc_id=npc.id,
        display_name=npc.name,
        visual_traits=visual_traits,
        has_visual_detail=bool(visual_traits),
    )


def build_location_presentation(
    db: Session, campaign_id: str, character_id: str, location_id: str
) -> LocationPresentation | None:
    """None means the location never made it into this character's own
    Map View at all — the caller must treat that exactly like Phase
    20's "no omniscient frontend" rule: nothing to show, not an
    error."""
    view = get_map_view(db, campaign_id, character_id)
    entry = next((location for location in view.locations if location.id == location_id), None)
    if entry is None:
        return None

    visual_traits = resolve_location_visual(db, campaign_id, location_id)
    return LocationPresentation(
        location_id=entry.id,
        display_name=entry.name,
        icon_category=entry.type,
        visual_traits=visual_traits,
        has_visual_detail=bool(visual_traits),
    )


def build_organization_presentation(db: Session, campaign_id: str, organization_id: str) -> OrganizationPresentation:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise VisualPresentationError(f"Organization {organization_id} does not exist.")

    spec = get_organization_visual_spec(db, campaign_id, organization_id)
    visual_traits = resolve_visual_layers(spec.stable, spec.current)
    return OrganizationPresentation(
        organization_id=organization.id,
        display_name=organization.name,
        icon_category=organization.organization_type,
        visual_traits=visual_traits,
        has_visual_detail=bool(visual_traits),
    )
