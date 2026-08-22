"""Phase 19M — Temporal Validator.

CURRENT != HISTORICAL (Phase 18's own core principle) applied to
narration: reuses app.ai.retrieval.documents.documents_historical
(Phase 18M's supersession mechanism) rather than a second temporal
index. If an organization's status was superseded (Phase 18M — e.g. an
ACTIVE guild that DISBANDED), narration asserting the OLD status as
still true is rejected — the spec's own worked example, shape for
shape (a rebuilt/destroyed bridge, an old vs new blacksmith).

Deliberately narrow: only organization status is checked (the one
production trigger Phase 18M actually wires today — see
app.services.event_log's ORGANIZATION_STATUS_CHANGED dispatch); a
Portuguese status-word vocabulary is used since that's the language the
Narrator actually writes in, not the raw English enum values Phase 18B
happens to store. No historical documents exist for anything else yet,
so this check is a safe no-op everywhere else.
"""
import re

from sqlalchemy.orm import Session

from app.ai.narrator import _mentions, _normalized
from app.ai.retrieval.temporal import documents_historical
from app.ai.validation.claims import ClaimCategory, NarrativeClaim
from app.ai.validation.contract import NarrativeProposal, Violation, register_validator
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType, OrganizationStatus
from app.db.models.organization import Organization

_STATUS_WORDS = {
    OrganizationStatus.ACTIVE: ("ativa", "ativo"),
    OrganizationStatus.DISBANDED: ("dissolvida", "dissolvido", "desfeita", "desfeito"),
    OrganizationStatus.DESTROYED: ("destruida", "destruido"),
    OrganizationStatus.DORMANT: ("dormente", "inativa", "inativo"),
    OrganizationStatus.ILLEGAL: ("ilegal",),
    OrganizationStatus.UNDERGROUND: ("clandestina", "clandestino"),
}


def _status_from_current_state_text(text: str) -> OrganizationStatus | None:
    match = re.search(r"status\s+(\w+)", text)
    if not match:
        return None
    try:
        return OrganizationStatus(match.group(1))
    except ValueError:
        return None


@register_validator
def validate_temporal_consistency(
    db: Session,
    campaign_id: str,
    proposal: NarrativeProposal,
    claims: list[NarrativeClaim],
) -> list[Violation]:
    historical_docs = documents_historical(
        db, campaign_id,
        source_types=[KnowledgeSourceType.ORGANIZATION],
        document_types=[KnowledgeDocumentType.CURRENT_STATE],
    )
    if not historical_docs:
        return []

    violations = []
    for old_doc in historical_docs:
        old_status = _status_from_current_state_text(old_doc.text)
        if old_status is None:
            continue
        organization = db.get(Organization, old_doc.source_id)
        if organization is None or organization.status == old_status.value:
            continue

        old_words = _STATUS_WORDS.get(old_status, ())
        if not old_words:
            continue

        for claim in claims:
            if not _mentions(claim.text, organization.name):
                continue
            normalized = _normalized(claim.text)
            if any(word in normalized for word in old_words):
                violations.append(
                    Violation(
                        claim_index=claim.index,
                        category=ClaimCategory.AUTHORITATIVE,
                        reason=(
                            f"'{claim.text}' descreve {organization.name} com um status "
                            f"("
                            f"{old_status.value}"
                            f") que já foi substituído por {organization.status}."
                        ),
                    )
                )
    return violations
