"""Phase 18H — Semantic Retrieval.

Uses the existing LLMService/Ollama provider abstraction (embed(), added
alongside generate() in app.ai.llm_service) rather than a new external
vector database — the game is single-user and local-first, and Ollama
already runs the same process narration/intent-parsing needs. No
external service, no pgvector: cosine similarity over a campaign's
already campaign-scoped, already access-controlled document set is
cheap at this corpus scale.

This module produces RANKED CANDIDATES only. It is a search tool, not a
final answer: Phase 18I's knowledge-aware filtering and Phase 18J's
temporal filtering still apply on top of whatever this returns before
anything reaches an LLM prompt — a high similarity score never implies
a knower may see the result.
"""
import json
import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService, LLMServiceError
from app.ai.retrieval.documents import current_documents
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.db.models.knowledge_index import IndexedKnowledgeDocument


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_document(db: Session, llm_service: LLMService, document: IndexedKnowledgeDocument) -> bool:
    """Generates and stores this document's embedding. Returns False (and
    leaves embedding_json untouched) if the configured LLMService does
    not support embeddings — an optional local model not being loaded is
    never a crash, only a smaller semantic candidate pool."""
    try:
        vector = llm_service.embed(document.text)
    except LLMServiceError:
        return False
    document.embedding_json = json.dumps(vector)
    db.flush()
    return True


@dataclass(frozen=True)
class ScoredDocument:
    document: IndexedKnowledgeDocument
    score: float


def semantic_search(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    query_text: str,
    *,
    source_types: list[KnowledgeSourceType] | None = None,
    document_types: list[KnowledgeDocumentType] | None = None,
    limit: int = 10,
) -> list[ScoredDocument]:
    """Campaign isolation is inherited from current_documents (a hard
    filter, never optional). Documents without a stored embedding yet
    (Phase 18M's index updates haven't re-embedded them, or embeddings
    are simply disabled) are silently excluded from candidates rather
    than scored as zero-relevance — an un-embedded document is a
    "not yet searchable" state, not a "definitely irrelevant" one."""
    try:
        query_vector = llm_service.embed(query_text)
    except LLMServiceError:
        return []

    candidates = current_documents(
        db, campaign_id, source_types=source_types, document_types=document_types
    )
    scored = []
    for document in candidates:
        if not document.embedding_json:
            continue
        vector = json.loads(document.embedding_json)
        scored.append(ScoredDocument(document, cosine_similarity(query_vector, vector)))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]
