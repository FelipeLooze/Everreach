"""Phase 18J — Temporal Retrieval.

CURRENT != HISTORICAL, and neither is decided by semantic similarity —
every mode here filters strictly on the world-clock fields Phase 18B
already put on IndexedKnowledgeDocument (occurred_world_minute,
is_current), never wall-clock time. CURRENT mode is exactly
app.ai.retrieval.documents.current_documents (the existing default);
this module adds the other modes the spec asks for on top of the same
table, rather than a parallel temporal index.

AT_TIME in particular answers "what was true at this world minute" by
picking, among ALL versions (current and superseded — Phase 18M) of the
same (source_type, source_id, document_type) key, whichever version's
occurred_world_minute is the latest one not after the requested minute.
This only produces meaningfully different answers once Phase 18M starts
superseding documents with multiple dated versions of the same key;
until then it degrades to whatever single version already exists.
"""
from sqlalchemy.orm import Query, Session

from app.ai.retrieval.documents import current_documents
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.db.models.knowledge_index import IndexedKnowledgeDocument


def _apply_type_filters(
    query: Query,
    source_types: list[KnowledgeSourceType] | None,
    document_types: list[KnowledgeDocumentType] | None,
) -> Query:
    if source_types:
        query = query.filter(
            IndexedKnowledgeDocument.source_type.in_([t.value for t in source_types])
        )
    if document_types:
        query = query.filter(
            IndexedKnowledgeDocument.document_type.in_([t.value for t in document_types])
        )
    return query


def documents_current(
    db: Session,
    campaign_id: str,
    *,
    source_types: list[KnowledgeSourceType] | None = None,
    document_types: list[KnowledgeDocumentType] | None = None,
) -> list[IndexedKnowledgeDocument]:
    return current_documents(db, campaign_id, source_types=source_types, document_types=document_types)


def documents_historical(
    db: Session,
    campaign_id: str,
    *,
    source_types: list[KnowledgeSourceType] | None = None,
    document_types: list[KnowledgeDocumentType] | None = None,
) -> list[IndexedKnowledgeDocument]:
    """Superseded documents only (is_current=False) — Phase 18M's job to
    produce any; this is empty until something actually supersedes a
    document."""
    query = db.query(IndexedKnowledgeDocument).filter(
        IndexedKnowledgeDocument.campaign_id == campaign_id,
        IndexedKnowledgeDocument.is_current.is_(False),
    )
    return _apply_type_filters(query, source_types, document_types).all()


def documents_recent(
    db: Session,
    campaign_id: str,
    current_world_minute: int,
    within_minutes: int,
    *,
    source_types: list[KnowledgeSourceType] | None = None,
    document_types: list[KnowledgeDocumentType] | None = None,
) -> list[IndexedKnowledgeDocument]:
    """Current documents whose occurred_world_minute falls in the last
    within_minutes — documents with no point-in-time meaning (NULL
    occurred_world_minute, e.g. a Region's general geography) never
    qualify as "recent"."""
    query = db.query(IndexedKnowledgeDocument).filter(
        IndexedKnowledgeDocument.campaign_id == campaign_id,
        IndexedKnowledgeDocument.is_current.is_(True),
        IndexedKnowledgeDocument.occurred_world_minute.isnot(None),
        IndexedKnowledgeDocument.occurred_world_minute >= current_world_minute - within_minutes,
        IndexedKnowledgeDocument.occurred_world_minute <= current_world_minute,
    )
    return _apply_type_filters(query, source_types, document_types).all()


def documents_during_period(
    db: Session,
    campaign_id: str,
    start_minute: int,
    end_minute: int,
    *,
    source_types: list[KnowledgeSourceType] | None = None,
    document_types: list[KnowledgeDocumentType] | None = None,
) -> list[IndexedKnowledgeDocument]:
    """Includes historical (superseded) documents by default — a period
    question ("what happened/was true then") is inherently about the
    past, not just what remains current today."""
    query = db.query(IndexedKnowledgeDocument).filter(
        IndexedKnowledgeDocument.campaign_id == campaign_id,
        IndexedKnowledgeDocument.occurred_world_minute.isnot(None),
        IndexedKnowledgeDocument.occurred_world_minute >= start_minute,
        IndexedKnowledgeDocument.occurred_world_minute <= end_minute,
    )
    return _apply_type_filters(query, source_types, document_types).all()


def documents_at_time(
    db: Session,
    campaign_id: str,
    at_minute: int,
    *,
    source_types: list[KnowledgeSourceType] | None = None,
    document_types: list[KnowledgeDocumentType] | None = None,
) -> list[IndexedKnowledgeDocument]:
    query = db.query(IndexedKnowledgeDocument).filter(
        IndexedKnowledgeDocument.campaign_id == campaign_id,
        IndexedKnowledgeDocument.occurred_world_minute.isnot(None),
        IndexedKnowledgeDocument.occurred_world_minute <= at_minute,
    )
    candidates = _apply_type_filters(query, source_types, document_types).all()

    best: dict[tuple[str, str, str], IndexedKnowledgeDocument] = {}
    for document in candidates:
        key = (document.source_type, document.source_id, document.document_type)
        current_best = best.get(key)
        if current_best is None or document.occurred_world_minute > current_best.occurred_world_minute:
            best[key] = document
    return list(best.values())
