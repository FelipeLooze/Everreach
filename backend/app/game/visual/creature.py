"""Phase 21F — Creature Visual Identity.

Audit finding this subphase is built around: no individual creature/
monster entity exists in Canon anywhere in this codebase — combat
actors are only CHARACTER/NPC/SIMULATED_PLAYER
(app.core.enums.CombatActorType). The one real "creature" concept that
DOES exist is app.db.models.regional_threat.RegionalThreat (Phase
15L): "a population/habitat abstraction (never an individual creature
instance)", its own docstring. That distinction — population/species
identity, never a per-animal instance — already IS the spec's own
SPECIES IDENTITY vs INDIVIDUAL CREATURE STATE split; ThreatType
(WOLVES, BOARS, ...) is the species-level Canon this subphase
visualizes.

Inventing an individual-creature entity here, just to have something
to attach "individual creature state" to, would be visual code
creating gameplay truth — exactly what the spec's core principle
forbids ("Visual design must come from Canon. Not the other way
around"). If a later phase adds real individual wildlife encounters,
its own Canon should be visualized then; nothing is speculatively
built for it now.

Species identity is campaign-global (subject_kind="threat_species",
keyed by ThreatType — the same "what does this concept look like
everywhere" scope app.game.visual.item uses for item definitions);
one specific RegionalThreat population (subject_kind="regional_threat",
campaign-scoped, since RegionalThreat rows themselves belong to one
subregion/campaign) may layer its own stable/current notes over that
species default (an unusually large pack, a habitat-specific
coloration note, ...).
"""
from sqlalchemy.orm import Session

from app.db.models.regional_threat import RegionalThreat
from app.game.visual.spec import (
    VisualSpec,
    get_visual_spec,
    resolve_visual_layers,
    set_current_visual_state,
    set_stable_visual_traits,
)


class CreatureVisualIdentityError(ValueError):
    pass


def set_threat_species_visual_identity(db: Session, threat_type: str, traits: dict) -> VisualSpec:
    return set_stable_visual_traits(db, "threat_species", threat_type, traits)


def get_threat_species_visual_identity(db: Session, threat_type: str) -> VisualSpec:
    return get_visual_spec(db, "threat_species", threat_type)


def set_regional_threat_current_state(
    db: Session, campaign_id: str, regional_threat_id: str, state: dict
) -> VisualSpec:
    return set_current_visual_state(db, "regional_threat", regional_threat_id, state, campaign_id=campaign_id)


def resolve_regional_threat_visual(db: Session, campaign_id: str, regional_threat_id: str) -> dict:
    threat = db.get(RegionalThreat, regional_threat_id)
    if threat is None:
        raise CreatureVisualIdentityError(f"Regional threat {regional_threat_id} does not exist.")

    species = get_threat_species_visual_identity(db, threat.threat_type).stable
    population = get_visual_spec(db, "regional_threat", regional_threat_id, campaign_id=campaign_id)

    return resolve_visual_layers(species, population.stable, population.current)
