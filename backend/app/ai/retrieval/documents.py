"""Phase 18B — the write/read primitives for IndexedKnowledgeDocument.

Every other retrieval subphase (semantic search, knowledge filtering,
temporal filtering, ranking...) reads through this module's queries;
none of them write documents directly. Population (which text goes in)
is each subphase's own concern (app.ai.retrieval.canon for 18B/18D,
historical events for 18C, memory consolidation for 18E, ...) — this
module only owns the storage shape.
"""
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.db.models.knowledge_index import IndexedKnowledgeDocument


def upsert_document(
    db: Session,
    campaign_id: str,
    source_type: KnowledgeSourceType,
    source_id: str,
    document_type: KnowledgeDocumentType,
    text: str,
    *,
    occurred_world_minute: int | None = None,
    source_version: str | None = None,
) -> IndexedKnowledgeDocument:
    """Create or refresh the one CURRENT chunk for (source, document_type).

    This is a plain refresh — it updates text in place and does not
    preserve what the text used to say. That is correct for straight
    re-derivation (nothing changed, or a cosmetic wording fix), but wrong
    for a fact that genuinely superseded an old one (a role changed, a
    bridge was destroyed) — that case is Phase 18M's
    supersede_document, which keeps the old row as historical instead of
    overwriting it.
    """
    existing = (
        db.query(IndexedKnowledgeDocument)
        .filter(
            IndexedKnowledgeDocument.campaign_id == campaign_id,
            IndexedKnowledgeDocument.source_type == source_type.value,
            IndexedKnowledgeDocument.source_id == source_id,
            IndexedKnowledgeDocument.document_type == document_type.value,
            IndexedKnowledgeDocument.is_current.is_(True),
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.text != text or existing.source_version != source_version:
            existing.text = text
            existing.source_version = source_version
            existing.occurred_world_minute = occurred_world_minute
            existing.embedding_json = None
            existing.generated_at = datetime.now(UTC).replace(tzinfo=None)
            db.flush()
        return existing

    document = IndexedKnowledgeDocument(
        campaign_id=campaign_id,
        source_type=source_type.value,
        source_id=source_id,
        document_type=document_type.value,
        text=text,
        occurred_world_minute=occurred_world_minute,
        source_version=source_version,
    )
    db.add(document)
    db.flush()
    return document


def documents_for_source(
    db: Session,
    campaign_id: str,
    source_type: KnowledgeSourceType,
    source_id: str,
    *,
    include_historical: bool = False,
) -> list[IndexedKnowledgeDocument]:
    query = db.query(IndexedKnowledgeDocument).filter(
        IndexedKnowledgeDocument.campaign_id == campaign_id,
        IndexedKnowledgeDocument.source_type == source_type.value,
        IndexedKnowledgeDocument.source_id == source_id,
    )
    if not include_historical:
        query = query.filter(IndexedKnowledgeDocument.is_current.is_(True))
    return query.order_by(IndexedKnowledgeDocument.document_type).all()


def documents_with_source_prefix(
    db: Session,
    campaign_id: str,
    source_type: KnowledgeSourceType,
    source_id_prefix: str,
    *,
    document_types: list[KnowledgeDocumentType] | None = None,
) -> list[IndexedKnowledgeDocument]:
    """For compound source_ids (Phase 18D's "{npc_id}:{character_id}"
    relationship pairing, Phase 18F's "{organization_id}:{action_id}"
    per-action institutional records) where callers need every document
    under one entity's id, not one exact compound key."""
    query = db.query(IndexedKnowledgeDocument).filter(
        IndexedKnowledgeDocument.campaign_id == campaign_id,
        IndexedKnowledgeDocument.source_type == source_type.value,
        IndexedKnowledgeDocument.source_id.like(f"{source_id_prefix}:%"),
        IndexedKnowledgeDocument.is_current.is_(True),
    )
    if document_types:
        query = query.filter(
            IndexedKnowledgeDocument.document_type.in_([t.value for t in document_types])
        )
    return query.order_by(IndexedKnowledgeDocument.generated_at.desc()).all()


def current_documents(
    db: Session,
    campaign_id: str,
    *,
    source_types: list[KnowledgeSourceType] | None = None,
    document_types: list[KnowledgeDocumentType] | None = None,
) -> list[IndexedKnowledgeDocument]:
    """Campaign is always a hard filter — never optional, per spec's
    Campaign isolation requirement."""
    query = db.query(IndexedKnowledgeDocument).filter(
        IndexedKnowledgeDocument.campaign_id == campaign_id,
        IndexedKnowledgeDocument.is_current.is_(True),
    )
    if source_types:
        query = query.filter(
            IndexedKnowledgeDocument.source_type.in_([t.value for t in source_types])
        )
    if document_types:
        query = query.filter(
            IndexedKnowledgeDocument.document_type.in_([t.value for t in document_types])
        )
    return query.all()
