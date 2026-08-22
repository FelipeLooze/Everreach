"""Phase 19O — Persistent Content Validator.

Phase 19C already classifies a claim as PERSISTENT_CANON via keyword
match (family relationships, secrets, organizations, settlements...);
Phase 19F's Canon Validator already rejects the settlement/geography/
organization portion of that vocabulary (it reuses app.ai.narrator.
_find_canon_violations' own _PERSISTENT_CONCEPTS list, which overlaps
with 19C's list for guilda/taverna/loja/vila/cidade/templo). This
module covers the genuinely uncovered remainder: a claim inventing a
NEW family relationship or secret about someone ("Osgar tem uma filha
secreta chamada Elena") — the spec's own worked example — is rejected
unless that relationship is already established in the scene context.

Deliberately narrow: only rejects when the claim is BOTH classified
PERSISTENT_CANON and matches this module's own family/secret
vocabulary specifically (not the settlement/geography words 19F
already owns), avoiding double-checking the same concept two different
ways.
"""
import re

from sqlalchemy.orm import Session

from app.ai.narrator import _normalized
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator

_FAMILY_OR_SECRET = re.compile(
    r"\b(filh[oa]|irma[oo]|esposa|marido|namorad[oa]|amante|segredo\w*|"
    r"casad[oa]|noiv[oa])\b",
    re.IGNORECASE,
)


@register_validator
def validate_persistent_content(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    context_has_it = bool(_FAMILY_OR_SECRET.search(_normalized(proposal.context)))
    if context_has_it:
        return []

    violations = []
    for claim in claims:
        if not claim.is_(ClaimCategory.PERSISTENT_CANON):
            continue
        if not _FAMILY_OR_SECRET.search(_normalized(claim.text)):
            continue
        violations.append(
            Violation(
                claim_index=claim.index,
                category=ClaimCategory.PERSISTENT_CANON,
                reason=(
                    f"'{claim.text}' cria um relacionamento familiar ou segredo persistente "
                    f"não estabelecido no cânone atual."
                ),
            )
        )
    return violations
