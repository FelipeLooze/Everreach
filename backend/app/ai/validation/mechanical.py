"""Phase 19N — Mechanical Outcome Validator.

Extends Phase 19I's exact same one-directional pattern (backend result
vs narrated claim, compared via mechanical_summary) from binary
success/failure to outcome INTENSITY: the spec's own examples — a
grazing hit narrated as a blade plunging into the chest, a navigation
failure narrated as effortlessly finding the trail — are intensity
mismatches, not simple success/failure contradictions Phase 19I already
catches.

Deliberately one-directional and narrow, same rationale as 19I (Phase
19G's lesson: an over-eager bidirectional check risks false rejections
on ordinary embellished-but-harmless prose). Only rejects narration
escalating a backend-recorded MINOR/harmless outcome into SEVERE
language — the direction that actually misleads the player about real
danger/consequences. The reverse (a severe outcome undersold in prose)
is weaker writing, not invented harm, and is not rejected.
"""
import re

from sqlalchemy.orm import Session

from app.ai.narrator import _normalized
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator

_MINOR_OUTCOME = re.compile(
    r"\b(de leve|arranha\w*|raspao|sem gravidade|ferimento leve|"
    r"nao\s+se\s+machuca\w*|falha\w*|erra\w*)\b",
    re.IGNORECASE,
)

_SEVERE_NARRATION = re.compile(
    r"\b(fatal\w*|mortal\w*|esmaga\w*|destroca\w*|estracalha\w*|"
    r"despedaca\w*|efetivamente|sem esforco|sem dificuldade)\b",
    re.IGNORECASE,
)


@register_validator
def validate_mechanical_intensity(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if not _MINOR_OUTCOME.search(_normalized(proposal.mechanical_summary)):
        return []

    violations = []
    for claim in claims:
        if _SEVERE_NARRATION.search(_normalized(claim.text)):
            violations.append(
                Violation(
                    claim_index=claim.index,
                    category=ClaimCategory.MECHANICAL,
                    reason=(
                        f"'{claim.text}' narra uma consequência severa, mas o resultado "
                        f"mecânico resolvido foi leve/sem gravidade "
                        f"({proposal.mechanical_summary!r})."
                    ),
                )
            )
    return violations
