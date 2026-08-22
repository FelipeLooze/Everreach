"""Phase 18K — Hybrid Ranking & Relevance.

A small, bounded, readable formula — not an opaque ML ranker (spec:
"avoid an incomprehensible machine-learning ranking system unless
genuinely needed"). Every signal is in [0, 1] and the weights are a
plain dict a caller can see and override.

HARD FILTERS VS SOFT RANKING: rank_documents re-applies Phase 18I's
knowledge-aware access check to every candidate before scoring it, and
silently drops anything inaccessible — a caller cannot accidentally let
a high semantic/recency/importance score smuggle an inaccessible
document into the final ranked list. Hard filters are never something
a ranking score can outweigh.
"""
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.orm import Session

from app.ai.retrieval.access import is_document_accessible_to
from app.ai.retrieval.semantic import ScoredDocument
from app.ai.retrieval.trace import log_retrieval_trace
from app.core.enums import KnowerType, KnowledgeDocumentType
from app.db.models.knowledge_index import IndexedKnowledgeDocument

RECENCY_HALF_LIFE_MINUTES = 60 * 24 * 30  # ~1 in-world month

DEFAULT_WEIGHTS = {
    "semantic": 0.5,
    "entity_match": 0.2,
    "recency": 0.15,
    "importance": 0.15,
}


@dataclass(frozen=True)
class RankedDocument:
    document: IndexedKnowledgeDocument
    score: float
    semantic_score: float
    entity_match: bool
    recency_score: float
    importance_score: float


def _importance_score(document: IndexedKnowledgeDocument) -> float:
    """Only HISTORICAL_EVENT documents carry a usable importance signal
    today (Phase 18C stashes the source WorldEvent's 1-5 importance in
    source_version) — everything else gets a neutral 0.5 rather than a
    fabricated number."""
    if document.document_type != KnowledgeDocumentType.HISTORICAL_EVENT.value:
        return 0.5
    try:
        importance = int(document.source_version)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, importance / 5.0))


def _recency_score(document: IndexedKnowledgeDocument, current_world_minute: int | None) -> float:
    if document.occurred_world_minute is None or current_world_minute is None:
        return 0.5
    age = max(0, current_world_minute - document.occurred_world_minute)
    return 1.0 / (1.0 + age / RECENCY_HALF_LIFE_MINUTES)


def _entity_match(document: IndexedKnowledgeDocument, scene_subjects: Sequence[str] | None) -> bool:
    if not scene_subjects:
        return False
    kind = document.source_type.lower()
    plain_id = document.source_id.split(":", 1)[0]
    return f"{kind}:{document.source_id}" in scene_subjects or f"{kind}:{plain_id}" in scene_subjects


def rank_documents(
    db: Session,
    campaign_id: str,
    scored_candidates: list[ScoredDocument],
    knower_type: KnowerType,
    knower_id: str,
    *,
    current_world_minute: int | None = None,
    scene_subjects: Sequence[str] | None = None,
    weights: dict[str, float] | None = None,
    limit: int = 10,
    query_description: str = "",
) -> list[RankedDocument]:
    weights = weights or DEFAULT_WEIGHTS
    ranked = []
    filtered_out_ids: set[str] = set()
    for scored in scored_candidates:
        document = scored.document
        if not is_document_accessible_to(db, campaign_id, document, knower_type, knower_id):
            filtered_out_ids.add(document.id)
            continue
        semantic_score = max(0.0, min(1.0, scored.score))
        entity_match = _entity_match(document, scene_subjects)
        recency_score = _recency_score(document, current_world_minute)
        importance_score = _importance_score(document)
        total = (
            weights["semantic"] * semantic_score
            + weights["entity_match"] * (1.0 if entity_match else 0.0)
            + weights["recency"] * recency_score
            + weights["importance"] * importance_score
        )
        ranked.append(
            RankedDocument(document, total, semantic_score, entity_match, recency_score, importance_score)
        )
    ranked.sort(key=lambda item: item.score, reverse=True)
    limited = ranked[:limit]

    # Phase 18S — a single trace call here covers every consumer that
    # already goes through this one chokepoint (Phase 18N's Context
    # Builder integration, and the new 18P/18Q/18R consumer functions)
    # without each needing its own logging.
    log_retrieval_trace(
        query_description, knower_type, knower_id, scored_candidates, filtered_out_ids, limited
    )
    return limited
