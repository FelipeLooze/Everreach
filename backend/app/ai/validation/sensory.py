"""Phase 19E — Sensory & Physiological Narration Policy.

Names and documents a distinction Phase 19C/19D already produce as a
side effect of how they work, rather than adding new detection logic:

SENSATION != EMOTION.

A sentence describing a physical/involuntary bodily experience (Phase
19C's SENSORY category) is always allowed, even about the protagonist,
provided it is phrased the way the spec's own valid examples are — the
sensation or an external cause as the grammatical subject ("o frio arde
na sua pele", "seu coração acelera"), never the protagonist's own name
as the subject of an interpreted-emotion or decision verb ("Logan sente
medo", "Logan decide fugir"). Phase 19D's validate_player_agency
already only rejects the latter shape (it reuses app.ai.narrator's
subject-position detection, which the spec's own valid sensory examples
are all phrased to avoid triggering) — this module exists to give that
already-real behavior an explicit name and a single place Phase 19S's
trace can point to when explaining why a sensory claim was allowed.

No validator is registered here: this module never rejects anything on
its own, it only classifies what Phase 19D already decided.
"""
from app.ai.validation.claims import ClaimCategory, NarrativeClaim


def is_sensory_claim(claim: NarrativeClaim) -> bool:
    return claim.is_(ClaimCategory.SENSORY)


def is_protected_sensory_claim(claim: NarrativeClaim) -> bool:
    """SENSORY and not also PLAYER_VOLUNTARY — genuinely safe under this
    policy. A claim that is BOTH (the spec's own "feels the wind and
    decides to return" example) is not fully protected: the voluntary
    half still makes the whole sentence rejectable at today's sentence-
    level repair granularity (a future Phase 19Q refinement could split
    it at clause level instead)."""
    return claim.is_(ClaimCategory.SENSORY) and not claim.is_(ClaimCategory.PLAYER_VOLUNTARY)
