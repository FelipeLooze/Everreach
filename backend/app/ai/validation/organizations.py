"""Phase 19L — Organization / Social Validator.

Reuses app.ai.retrieval.organizations.is_active_organization_member
(Phase 18F/18I) rather than a second membership-checking mechanism — a
narrated claim of the protagonist's own organizational membership
("Como membro da Guilda dos Mercadores...") is checked against the
exact same ACTIVE-membership gate Phase 18's retrieval layer already
enforces for institutional knowledge access.

Deliberately narrow: only the "como membro de {organization}" claim
shape is recognized (a curated pattern, not general NLP); an
organization name that doesn't match any real Organization.name in the
campaign is never guessed at or flagged — silence, not a false
rejection, when the check cannot be made reliably (Phase 19G's lesson).
"""
import re

from sqlalchemy.orm import Session

from app.ai.retrieval.organizations import is_active_organization_member
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.core.enums import CombatActorType
from app.db.models.organization import Organization

_MEMBERSHIP_CLAIM = re.compile(
    r"\bcomo\s+membro\s+d[aoe]s?\s+([A-ZÀ-Ý][\wÀ-ÿ' -]+?)(?:[,.]|$)", re.IGNORECASE
)


@register_validator
def validate_organization_membership(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    if not proposal.character_id:
        return []

    violations = []
    for claim in claims:
        match = _MEMBERSHIP_CLAIM.search(claim.text)
        if not match:
            continue
        organization_name = match.group(1).strip()
        organization = (
            db.query(Organization)
            .filter(
                Organization.campaign_id == campaign_id,
                Organization.name.ilike(organization_name),
            )
            .first()
        )
        if organization is None:
            continue
        if not is_active_organization_member(
            db, organization.id, CombatActorType.CHARACTER, proposal.character_id
        ):
            violations.append(
                Violation(
                    claim_index=claim.index,
                    category=ClaimCategory.AUTHORITATIVE,
                    reason=(
                        f"'{claim.text}' reivindica associação com {organization.name}, mas o "
                        f"personagem não é um membro ativo."
                    ),
                )
            )
    return violations
