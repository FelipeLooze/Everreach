"""Phase 18I — Knowledge-Aware Retrieval.

The one hard-filter dispatcher every retrieval consumer runs a candidate
through before it ever reaches an LLM prompt: semantic candidate ->
does the current actor know/have access? NO -> discard. Never let
embedding similarity leak a secret.

Reuses whatever access story already exists for a source_type instead
of inventing a fourth one: Phase 18G's geographic Knowledge gate,
Phase 18F's organization membership gate, and — new here — an NPC
"has this knower actually met/is this NPC" gate and an own-memory-only
gate for Phase 18E's consolidated summaries. A source_type with no
established access story (currently: EVENT) is denied by default —
relevance never substitutes for access.
"""
from sqlalchemy.orm import Session

from app.ai.retrieval.documents import current_documents
from app.ai.retrieval.geography import (
    GEOGRAPHIC_SOURCE_TYPES,
    SOURCE_TYPE_TO_SUBJECT_KIND,
    knows_about_geographic_subject,
)
from app.ai.retrieval.organizations import is_active_organization_member
from app.core.enums import (
    CombatActorType,
    KnowerType,
    KnowledgeDocumentType,
    KnowledgeSourceType,
)
from app.db.models.knowledge_index import IndexedKnowledgeDocument
from app.db.models.organization import Organization
from app.game.relationships.service import get_character_npc_relationship

_KNOWER_TO_ACTOR_TYPE = {
    KnowerType.PLAYER: CombatActorType.CHARACTER,
    KnowerType.NPC: CombatActorType.NPC,
    KnowerType.SIMULATED_PLAYER: CombatActorType.SIMULATED_PLAYER,
}

_MEMORY_SOURCE_TYPE_TO_KNOWER_TYPE = {
    KnowledgeSourceType.CHARACTER: KnowerType.PLAYER,
    KnowledgeSourceType.SIMULATED_PLAYER: KnowerType.SIMULATED_PLAYER,
}


def _geographic_access(
    db: Session, campaign_id: str, document: IndexedKnowledgeDocument,
    knower_type: KnowerType, knower_id: str,
) -> bool:
    kind = SOURCE_TYPE_TO_SUBJECT_KIND.get(KnowledgeSourceType(document.source_type))
    if kind is None:
        return False
    return knows_about_geographic_subject(
        db, campaign_id, knower_type, knower_id, f"{kind}:{document.source_id}"
    )


def _organization_access(
    db: Session, document: IndexedKnowledgeDocument, knower_type: KnowerType, knower_id: str
) -> bool:
    actor_type = _KNOWER_TO_ACTOR_TYPE.get(knower_type)

    if document.document_type == KnowledgeDocumentType.IMPORTANT_HISTORY.value:
        # Institutional records (Phase 18F): membership required, no
        # exceptions for public organizations — an outsider never sees
        # internal history just because the organization itself is public.
        organization_id = document.source_id.split(":", 1)[0]
        if actor_type is None:
            return False
        return is_active_organization_member(db, organization_id, actor_type, knower_id)

    # IDENTITY/CURRENT_STATE (Phase 18B): mirrors context_builder's own
    # "PUBLIC organizations, or actual members" visibility rule — never a
    # new, different one.
    organization = db.get(Organization, document.source_id)
    if organization is None:
        return False
    if organization.visibility == "PUBLIC":
        return True
    if actor_type is None:
        return False
    return is_active_organization_member(db, organization.id, actor_type, knower_id)


def _npc_access(
    db: Session, campaign_id: str, document: IndexedKnowledgeDocument,
    knower_type: KnowerType, knower_id: str,
) -> bool:
    if ":" in document.source_id:
        # RELATIONSHIP pair document "{npc_id}:{character_id}" (Phase
        # 18D) — only the two participants may see their own record.
        npc_id, character_id = document.source_id.split(":", 1)
        if knower_type == KnowerType.NPC and knower_id == npc_id:
            return True
        return knower_type == KnowerType.PLAYER and knower_id == character_id

    # IDENTITY/BACKGROUND — "private NPC context" (context_builder's own
    # label): visible once this knower has actually met the NPC (a
    # relationship row exists), never merely because it is indexed.
    if knower_type == KnowerType.NPC and knower_id == document.source_id:
        return True
    if knower_type == KnowerType.PLAYER:
        return get_character_npc_relationship(db, campaign_id, knower_id, document.source_id) is not None
    return False


def _own_memory_access(
    document: IndexedKnowledgeDocument, knower_type: KnowerType, knower_id: str
) -> bool:
    expected_knower_type = _MEMORY_SOURCE_TYPE_TO_KNOWER_TYPE.get(
        KnowledgeSourceType(document.source_type)
    )
    if expected_knower_type is None or knower_type != expected_knower_type:
        return False
    owner_id = document.source_id.split(":", 1)[0]
    return knower_id == owner_id


def is_document_accessible_to(
    db: Session,
    campaign_id: str,
    document: IndexedKnowledgeDocument,
    knower_type: KnowerType,
    knower_id: str,
) -> bool:
    source_type = KnowledgeSourceType(document.source_type)

    if source_type in GEOGRAPHIC_SOURCE_TYPES:
        return _geographic_access(db, campaign_id, document, knower_type, knower_id)
    if source_type == KnowledgeSourceType.ORGANIZATION:
        return _organization_access(db, document, knower_type, knower_id)
    if source_type == KnowledgeSourceType.NPC:
        return _npc_access(db, campaign_id, document, knower_type, knower_id)
    if source_type in (KnowledgeSourceType.CHARACTER, KnowledgeSourceType.SIMULATED_PLAYER):
        return _own_memory_access(document, knower_type, knower_id)

    # EVENT and any future source_type: no established per-knower access
    # story yet — deny by default rather than let a semantic candidate
    # slip through unfiltered.
    return False


def knowledge_aware_filter(
    db: Session,
    campaign_id: str,
    documents: list[IndexedKnowledgeDocument],
    knower_type: KnowerType,
    knower_id: str,
) -> list[IndexedKnowledgeDocument]:
    return [
        document
        for document in documents
        if is_document_accessible_to(db, campaign_id, document, knower_type, knower_id)
    ]


def knowledge_aware_documents(
    db: Session,
    campaign_id: str,
    knower_type: KnowerType,
    knower_id: str,
    *,
    source_types: list[KnowledgeSourceType] | None = None,
    document_types: list[KnowledgeDocumentType] | None = None,
) -> list[IndexedKnowledgeDocument]:
    """Convenience entry point for a consumer that doesn't need semantic
    ranking at all (spec: semantic search identifies candidates, it does
    not by itself construct final context — a consumer is free to skip
    it and go straight from "every current document" to "what this
    knower may see")."""
    candidates = current_documents(
        db, campaign_id, source_types=source_types, document_types=document_types
    )
    return knowledge_aware_filter(db, campaign_id, candidates, knower_type, knower_id)
