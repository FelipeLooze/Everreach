"""Phase 18F — Organization Long-Term Memory.

OrganizationAction (Phase 13K) already IS the organization's append-only
institutional action log — this indexes those rows rather than building
a second "organization memory" table. Distinct from Phase 18D/18E's
NPC/character memory: institutional knowledge belongs to the
organization, not to any one member, and is gated by ACTIVE membership
(reusing OrganizationMembershipStatus — the same status
context_builder.py already checks for "Member"/"Not a member" display),
never by a member's own personal Memory rows.
"""
from sqlalchemy.orm import Session

from app.ai.retrieval.documents import documents_with_source_prefix, upsert_document
from app.core.enums import (
    CombatActorType,
    KnowledgeDocumentType,
    KnowledgeSourceType,
    OrganizationMembershipStatus,
)
from app.db.models.knowledge_index import IndexedKnowledgeDocument
from app.db.models.organization import Organization, OrganizationAction, OrganizationMember


def index_organization_action(db: Session, action: OrganizationAction) -> IndexedKnowledgeDocument | None:
    organization = db.get(Organization, action.organization_id)
    if organization is None:
        return None
    return upsert_document(
        db,
        organization.campaign_id,
        KnowledgeSourceType.ORGANIZATION,
        f"{organization.id}:{action.id}",
        KnowledgeDocumentType.IMPORTANT_HISTORY,
        action.description,
        occurred_world_minute=action.world_minute,
    )


def is_active_organization_member(
    db: Session,
    organization_id: str,
    member_type: CombatActorType,
    member_id: str,
) -> bool:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.member_type == member_type.value,
            OrganizationMember.member_id == member_id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE.value,
        )
        .first()
        is not None
    )


def institutional_memory_for_member(
    db: Session,
    campaign_id: str,
    organization_id: str,
    member_type: CombatActorType,
    member_id: str,
) -> list[IndexedKnowledgeDocument]:
    """Institutional memory is only visible to a currently ACTIVE member —
    never to an outsider, no matter how semantically relevant a candidate
    document is (spec: RELEVANT != ALLOWED). This is a hard membership
    gate, not the finer role/permission granularity the spec allows for
    later ("do not build excessive document-security simulation unless
    needed, but keep architecture compatible") — a suspended/expelled/
    former member sees nothing here either, matching how
    OrganizationMembershipStatus already gates everything else."""
    if not is_active_organization_member(db, organization_id, member_type, member_id):
        return []
    return documents_with_source_prefix(
        db,
        campaign_id,
        KnowledgeSourceType.ORGANIZATION,
        organization_id,
        document_types=[KnowledgeDocumentType.IMPORTANT_HISTORY],
    )
