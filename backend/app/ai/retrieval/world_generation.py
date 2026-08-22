"""Phase 18R — World Generator Retrieval.

The World Generator (app/game/world/*.py, Phase 15/16) is 100%
procedural — Phase 18A's audit found zero LLM calls anywhere in that
package, so there is no LLM consumer to feed this context to today.
This module builds the retrieval CAPABILITY the spec describes (before
generating new persistent content, retrieve relevant existing Canon to
reduce contradictions) as a standalone, tested primitive; nothing here
is wired into app/game/world/generator.py's actual generation calls.

UNLIKE every other consumer (18N-18Q), this is NEVER knowledge-gated:
the spec's own example is about CONSISTENCY ("continuing rivers/roads,
existing rumors, established names"), a system-level Canon-authoring
concern, not any one character/NPC/organization's limited perspective —
the World Generator, like the Game Engine itself, needs full Canon
visibility. It therefore does not call
app.ai.retrieval.ranking.rank_documents (which always requires a
knower and always applies Phase 18I's access gate); it reuses that
same module's underlying scoring building blocks directly instead.
"""
from sqlalchemy.orm import Session

from app.ai.retrieval.budget import fit_to_budget, format_ranked_documents
from app.ai.retrieval.documents import current_documents
from app.ai.retrieval.ranking import RankedDocument, _entity_match, _importance_score, _recency_score
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType

WORLD_GENERATION_CONTEXT_CHAR_BUDGET = 3000

_CANON_DOCUMENT_TYPES = [KnowledgeDocumentType.IDENTITY, KnowledgeDocumentType.BACKGROUND]


def build_world_generation_context(
    db: Session,
    campaign_id: str,
    *,
    near_source_types: list[KnowledgeSourceType] | None = None,
    scene_subjects: list[str] | None = None,
    current_world_minute: int | None = None,
) -> str:
    candidates = current_documents(
        db, campaign_id, source_types=near_source_types, document_types=_CANON_DOCUMENT_TYPES,
    )

    ranked = []
    for document in candidates:
        entity_match = _entity_match(document, scene_subjects)
        recency_score = _recency_score(document, current_world_minute)
        importance_score = _importance_score(document)
        score = (
            0.5 * (1.0 if entity_match else 0.0)
            + 0.25 * recency_score
            + 0.25 * importance_score
        )
        ranked.append(
            RankedDocument(document, score, 0.0, entity_match, recency_score, importance_score)
        )
    ranked.sort(key=lambda item: item.score, reverse=True)

    budgeted = fit_to_budget(ranked, max_chars=WORLD_GENERATION_CONTEXT_CHAR_BUDGET)
    if not budgeted.included:
        return "EXISTING CANON\n- none recalled"
    return format_ranked_documents(budgeted.included)
