"""Phase 21N — Canon Entity Visual Metadata.

Audit this subphase performed: every entity table across the whole
codebase was checked for a new visual/style column added instead of
using app.game.visual.spec's shared VisualIdentity store (21C) — none
was found; every concrete visual module (21D-21J) writes exclusively
through that one table. No frontend-only UI state (selected/hovered/
panel_open — see e.g. InteractiveMap.tsx's own useState) is persisted
here either; "VISUAL METADATA IS NOT UI STATE" (spec, mandatory) holds
because nothing in this package, or its callers, ever sends transient
presentation state to the backend as Canon.

VISUAL_SUBJECT_KINDS below is the one thing that audit did not already
have anywhere: a single, discoverable registry of every subject_kind
app.game.visual.spec.VisualIdentity legitimately stores data for, and
why. It is documentation, not a validation gate — a new subphase may
introduce a new subject_kind without being blocked here — but every
kind actually in use today is listed, so a future reader never has to
grep five files to find them all.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualSubjectKind:
    key: str
    campaign_scoped: bool
    description: str


VISUAL_SUBJECT_KINDS: tuple[VisualSubjectKind, ...] = (
    VisualSubjectKind("npc", True, "Phase 21E — NPC stable identity + current appearance."),
    VisualSubjectKind(
        "item_definition", False,
        "Phase 21D — an item definition's optional signature_ornamentation. "
        "Global like the item catalog itself (app.db.models.item.ItemDefinition).",
    ),
    VisualSubjectKind("location", True, "Phase 21G — a Location's base identity + current scene state."),
    VisualSubjectKind("settlement", True, "Phase 21H — a Settlement's own traits, layered over its Location's."),
    VisualSubjectKind("region", True, "Phase 21I — a Region's broad visual tendency."),
    VisualSubjectKind("subregion", True, "Phase 21I — a Subregion's own tendency, overriding its Region's."),
    VisualSubjectKind("organization", True, "Phase 21J — an organization's persistent heraldry/symbol Canon."),
    VisualSubjectKind(
        "threat_species", False,
        "Phase 21F — species-level appearance for a ThreatType (WOLVES, ...). "
        "Global: what a species looks like is not a per-campaign fact.",
    ),
    VisualSubjectKind(
        "regional_threat", True,
        "Phase 21F — one specific RegionalThreat population's own notes, "
        "layered over its species' default.",
    ),
)


def describe_visual_subject_kind(key: str) -> VisualSubjectKind | None:
    return next((kind for kind in VISUAL_SUBJECT_KINDS if kind.key == key), None)
