from sqlalchemy.orm import Session

from app.core.enums import TechniqueMasteryTier
from app.db.models.skill import CharacterTechnique

# Deliberately not "more mastery = more damage" (see Phase 11 spec). The one
# mechanical effect implemented here is execution reliability: a small bonus
# toward actually landing the technique, consumed by both the generic skill
# check (resolve_technique_use) and the combat attack roll
# (resolve_combat_technique). Both read through the tier, never the raw
# float — the tier is the single source of truth for what mastery means,
# mechanically and to the player, so the two can never drift apart.

_MASTERY_TIER_THRESHOLDS: tuple[tuple[TechniqueMasteryTier, float], ...] = (
    (TechniqueMasteryTier.MASTERED, 30.0),
    (TechniqueMasteryTier.REFINED, 15.0),
    (TechniqueMasteryTier.PRACTICED, 6.0),
    (TechniqueMasteryTier.BASIC, 1.0),
)

_MASTERY_TIER_RELIABILITY_BONUS: dict[TechniqueMasteryTier, int] = {
    TechniqueMasteryTier.UNSTABLE: 0,
    TechniqueMasteryTier.BASIC: 1,
    TechniqueMasteryTier.PRACTICED: 2,
    TechniqueMasteryTier.REFINED: 4,
    TechniqueMasteryTier.MASTERED: 6,
}


def technique_mastery_tier(mastery: float) -> TechniqueMasteryTier:
    for tier, threshold in _MASTERY_TIER_THRESHOLDS:
        if mastery >= threshold:
            return tier
    return TechniqueMasteryTier.UNSTABLE


def technique_mastery_reliability_bonus(mastery: float) -> int:
    return _MASTERY_TIER_RELIABILITY_BONUS[technique_mastery_tier(mastery)]


def character_technique_mastery_tier(
    db: Session,
    character_id: str,
    technique_id: str,
) -> TechniqueMasteryTier:
    """Read-only lookup for display — e.g. the character sheet. Absence of a
    row (should not happen for a technique already filtered to LEARNED) is
    treated as UNSTABLE rather than raising, since this is presentation, not
    a mechanical gate."""
    link = (
        db.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character_id,
            CharacterTechnique.technique_id == technique_id,
        )
        .one_or_none()
    )
    return technique_mastery_tier(link.mastery if link is not None else 0.0)


def award_technique_mastery(
    db: Session,
    character_id: str,
    technique_id: str,
    *,
    amount: float,
) -> CharacterTechnique:
    """Grow a LEARNED technique's mastery from actual use. Uncapped, same as
    every other progression value in this project — MASTERED is a threshold
    to cross, not a ceiling to hit."""
    if amount <= 0:
        raise ValueError("Technique mastery gain must be positive.")
    link = (
        db.query(CharacterTechnique)
        .filter(
            CharacterTechnique.character_id == character_id,
            CharacterTechnique.technique_id == technique_id,
        )
        .one_or_none()
    )
    if link is None:
        raise ValueError("Character does not have a relationship with this technique.")
    link.mastery += amount
    db.flush()
    return link
