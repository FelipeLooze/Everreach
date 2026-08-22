"""Phase 18P — NPC Decision Retrieval.

No NPC decision-making LLM engine exists in this codebase (Phase 18A's
audit confirmed: NPCs act via pure rule-based simulation,
app.simulation.npc_simulation, never an LLM call) — this module builds
the CONSUMER-SPECIFIC retrieval policy a future NPC decision engine
would need, on the exact same shared pipeline every other consumer
(18N/18O/18Q/18R) already uses. Nothing here is wired into gameplay; it
exists and is tested standalone so a future NPC decision engine has
this ready rather than needing its own retrieval integration built
from scratch.

Per spec: "Give an NPC only what they know, what they believe, what
they remember, relevant goals, accessible organization knowledge" —
never omniscient backend truth. Every candidate set is gated by
knowledge_aware_documents (18I) for THIS NPC specifically, exactly like
every other consumer.
"""
from sqlalchemy.orm import Session

from app.ai.retrieval.access import knowledge_aware_documents
from app.ai.retrieval.budget import fit_to_budget, format_ranked_documents
from app.ai.retrieval.geography import geographic_documents_known_to
from app.ai.retrieval.organizations import institutional_memory_for_member
from app.ai.retrieval.ranking import rank_documents
from app.ai.retrieval.semantic import ScoredDocument
from app.core.enums import CombatActorType, KnowerType, KnowledgeDocumentType, OrganizationMembershipStatus
from app.db.models.npc import NPC
from app.db.models.organization import OrganizationMember

NPC_DECISION_CONTEXT_CHAR_BUDGET = 2000

_NPC_DECISION_DOCUMENT_TYPES = [
    KnowledgeDocumentType.IDENTITY,
    KnowledgeDocumentType.BACKGROUND,
    KnowledgeDocumentType.RELATIONSHIP,
    KnowledgeDocumentType.IMPORTANT_HISTORY,
]


def build_npc_decision_context(
    db: Session,
    campaign_id: str,
    npc: NPC,
    *,
    current_world_minute: int | None = None,
) -> str:
    own_candidates = knowledge_aware_documents(
        db, campaign_id, KnowerType.NPC, npc.id, document_types=_NPC_DECISION_DOCUMENT_TYPES,
    )
    ranked = rank_documents(
        db, campaign_id,
        [ScoredDocument(document, 0.0) for document in own_candidates],
        KnowerType.NPC, npc.id,
        current_world_minute=current_world_minute,
        query_description=f"NPC Decision: {npc.name}'s own knowledge/memory",
    )

    geographic = geographic_documents_known_to(db, campaign_id, KnowerType.NPC, npc.id)
    ranked += rank_documents(
        db, campaign_id,
        [ScoredDocument(document, 0.0) for document in geographic],
        KnowerType.NPC, npc.id,
        current_world_minute=current_world_minute,
        query_description=f"NPC Decision: {npc.name}'s geographic knowledge",
    )

    memberships = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.member_type == CombatActorType.NPC.value,
            OrganizationMember.member_id == npc.id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE.value,
        )
        .all()
    )
    for membership in memberships:
        institutional = institutional_memory_for_member(
            db, campaign_id, membership.organization_id, CombatActorType.NPC, npc.id,
        )
        ranked += rank_documents(
            db, campaign_id,
            [ScoredDocument(document, 0.0) for document in institutional],
            KnowerType.NPC, npc.id,
            current_world_minute=current_world_minute,
            query_description=f"NPC Decision: {npc.name}'s organization knowledge",
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    budgeted = fit_to_budget(ranked, max_chars=NPC_DECISION_CONTEXT_CHAR_BUDGET)
    if not budgeted.included:
        return "NPC KNOWLEDGE\n- none recalled"
    return format_ranked_documents(budgeted.included)
