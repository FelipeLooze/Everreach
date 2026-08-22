"""Phase 18Q — Organization Decision Retrieval.

No Organization decision-making LLM engine exists in this codebase
(Phase 18A's audit found no LLM-driven organization AI anywhere;
organizations act through app.game.organizations' rule-based service
layer) — same rationale and shape as Phase 18P's NPC Decision
Retrieval: this builds the consumer-specific retrieval policy a future
organization decision engine would need, on the same shared pipeline.
Nothing here is wired into gameplay.

Per spec: "current goals, needs, resources, recent important events,
economic situation, allies/enemies, institutional memory, accessible
regional knowledge... organization knowledge must come from reports,
members, records, direct activities, intelligence." Goals/needs/
treasury (OrganizationGoal/OrganizationNeed/Organization.treasury,
Phase 13I/13J) are already direct authoritative database state —
per Phase 18's own "current state should not rely on the embedding
index" rule, a real future consumer would read those directly, not
through retrieval; this module covers only the RETRIEVABLE long-term
half: institutional history and geographic knowledge, both scoped to
the ORGANIZATION as its own knower (Phase 17O's KnowerType.ORGANIZATION).
An organization always has full access to its own institutional
records (app.ai.retrieval.access's self-access rule, added this
subphase) independent of any one member's status.
"""
from sqlalchemy.orm import Session

from app.ai.retrieval.budget import fit_to_budget, format_ranked_documents
from app.ai.retrieval.documents import documents_with_source_prefix
from app.ai.retrieval.geography import geographic_documents_known_to
from app.ai.retrieval.ranking import rank_documents
from app.ai.retrieval.semantic import ScoredDocument
from app.core.enums import KnowerType, KnowledgeDocumentType, KnowledgeSourceType
from app.db.models.organization import Organization

ORGANIZATION_DECISION_CONTEXT_CHAR_BUDGET = 2000


def build_organization_decision_context(
    db: Session,
    campaign_id: str,
    organization: Organization,
    *,
    current_world_minute: int | None = None,
) -> str:
    institutional = documents_with_source_prefix(
        db, campaign_id, KnowledgeSourceType.ORGANIZATION, organization.id,
        document_types=[KnowledgeDocumentType.IMPORTANT_HISTORY],
    )
    ranked = rank_documents(
        db, campaign_id,
        [ScoredDocument(document, 0.0) for document in institutional],
        KnowerType.ORGANIZATION, organization.id,
        current_world_minute=current_world_minute,
        query_description=f"Organization Decision: {organization.name}'s institutional memory",
    )

    geographic = geographic_documents_known_to(
        db, campaign_id, KnowerType.ORGANIZATION, organization.id,
    )
    ranked += rank_documents(
        db, campaign_id,
        [ScoredDocument(document, 0.0) for document in geographic],
        KnowerType.ORGANIZATION, organization.id,
        current_world_minute=current_world_minute,
        query_description=f"Organization Decision: {organization.name}'s geographic knowledge",
    )

    ranked.sort(key=lambda item: item.score, reverse=True)
    budgeted = fit_to_budget(ranked, max_chars=ORGANIZATION_DECISION_CONTEXT_CHAR_BUDGET)
    if not budgeted.included:
        return "ORGANIZATION KNOWLEDGE\n- none recalled"
    return format_ranked_documents(budgeted.included)
