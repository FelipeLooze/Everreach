"""Phase 19D — Player Agency Validator.

DEFENSE IN DEPTH, not the primary defense: app.ai.narrator.narrate()
already strips protagonist-agency violations before ever returning (its
own _protagonist_agency_violations / _fabricated_turn_violations pass,
plus a bounded revision loop and granular sentence-dropping). In the
normal app.game.engine flow, text reaching this pipeline has therefore
already had voluntary-protagonist-action claims removed — this
validator exists for any text that reaches validate_narrative_proposal
by a path that did not go through narrator.narrate() first (a future
direct caller, a test), and to make agency violations show up in
NarrativeValidationResult.violations for Phase 19S's trace, which
narrator.py's own internal checks never expose outside a log line.

Classification (Phase 19C) already did the actual detection work —
this validator only turns every claim classify_claim tagged
PLAYER_VOLUNTARY into a Violation. Sensory/physiological claims (Phase
19E) are a DIFFERENT category entirely and are never touched here, even
when they co-occur with a rejected voluntary claim in the same sentence
(the spec's own "feels the wind and decides to return" example) — the
whole sentence is dropped only because narrator.py's own subject-
position detection (reused by classify_claim) found a real agency verb
with the protagonist as its subject, not because it mentions a
sensation.
"""
from sqlalchemy.orm import Session

from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator


@register_validator
def validate_player_agency(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    return [
        Violation(
            claim_index=claim.index,
            category=ClaimCategory.PLAYER_VOLUNTARY,
            reason=(
                f"'{claim.text}' atribui uma ação/decisão/fala voluntária ao "
                f"protagonista sem suporte no input do jogador."
            ),
        )
        for claim in claims
        if claim.is_(ClaimCategory.PLAYER_VOLUNTARY)
    ]
