"""Phase 19F — Canon Validator.

DEFENSE IN DEPTH, same rationale as Phase 19D: app.ai.narrator.narrate()
already runs _find_canon_violations against the full draft (persistent
concepts unsupported by context, quantified history, rumor attribution,
invented calendar/history, unregistered route+direction combinations)
before ever returning, revising when it fires. Text reaching this
pipeline through the normal app.game.engine flow has therefore already
been checked once. This re-applies the SAME function — not a second,
divergent canon-checking system — per claim (Phase 19B granularity)
so violations are exposed in NarrativeValidationResult.violations
(Phase 19S's trace) and so text reaching this pipeline by any other
path is still caught.
"""
from sqlalchemy.orm import Session

from app.ai.narrator import _find_canon_violations
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator


@register_validator
def validate_canon(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    violations = []
    for claim in claims:
        for reason in _find_canon_violations(claim.text, proposal.context, proposal.player_input):
            violations.append(
                Violation(claim_index=claim.index, category=ClaimCategory.AUTHORITATIVE, reason=reason)
            )
    return violations
