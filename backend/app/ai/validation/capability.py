"""Phase 19I — Character Capability Validator.

Genuinely new: narrator.py has the resolved mechanical_summary text
available in its prompt but never cross-checks its OWN output against
it — it only checks the produced text against canon/agency/knowledge
concerns, not against the mechanical result. The backend
(app.game.combat, app.game.skills, ...) is the sole authority on
whether an attempted action succeeded or failed; the Narrator may only
describe that already-resolved outcome, never independently declare a
success the backend recorded as a failure.

Deliberately narrow and one-directional (spec: "do not overcorrect"):
only rejects narration claiming SUCCESS when the resolved outcome was
FAILURE. The reverse (backend succeeded, narration undersells it) is
weaker prose, not an invented capability, and is not rejected here.
Full outcome-intensity matching (grazing hit narrated as a fatal blow)
is Phase 19N's job, building on this same mechanical_summary
comparison.
"""
import re

from sqlalchemy.orm import Session

from app.ai.narrator import _normalized
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator

_SUCCESS_LANGUAGE = re.compile(
    r"\b(consegue\w*|com sucesso|efetivamente|sem dificuldade|facilmente)\b", re.IGNORECASE
)
_FAILURE_LANGUAGE = re.compile(
    r"\b(falha\w*|fracassa\w*|nao consegue\w*|erra\w*|em vao)\b", re.IGNORECASE
)


@register_validator
def validate_character_capability(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if not _FAILURE_LANGUAGE.search(_normalized(proposal.mechanical_summary)):
        return []

    violations = []
    for claim in claims:
        normalized = _normalized(claim.text)
        if _SUCCESS_LANGUAGE.search(normalized) and not _FAILURE_LANGUAGE.search(normalized):
            violations.append(
                Violation(
                    claim_index=claim.index,
                    category=ClaimCategory.MECHANICAL,
                    reason=(
                        f"'{claim.text}' narra sucesso, mas o resultado mecânico resolvido "
                        f"foi falha ({proposal.mechanical_summary!r})."
                    ),
                )
            )
    return violations
