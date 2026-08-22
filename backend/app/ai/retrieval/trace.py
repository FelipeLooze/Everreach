"""Phase 18S — Retrieval Validation & Observability.

Developer/debug information ONLY — logged at DEBUG level (same
convention as app.ai.validation.trace's Phase 19S narrative trace),
never returned to a caller and never part of anything that could reach
the player. Mirrors the spec's own worked example format exactly:
per-candidate semantic score, FILTERED (with a reason) or SELECTED
(with a final score).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.ai.retrieval.ranking import RankedDocument
    from app.ai.retrieval.semantic import ScoredDocument
    from app.core.enums import KnowerType

logger = get_logger("context")


def log_retrieval_trace(
    query_description: str,
    knower_type: "KnowerType",
    knower_id: str,
    candidates: "list[ScoredDocument]",
    filtered_out_ids: set[str],
    ranked: "list[RankedDocument]",
) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return

    ranked_by_id = {ranked_doc.document.id: ranked_doc for ranked_doc in ranked}
    lines = [
        "RETRIEVAL TRACE",
        f"Query: {query_description}",
        f"Knower: {knower_type}:{knower_id}",
        "",
    ]
    for scored in candidates:
        document = scored.document
        lines.append(f"Candidate: {document.source_type}:{document.source_id} ({document.document_type})")
        lines.append(f"  semantic = {scored.score:.2f}")
        if document.id in filtered_out_ids:
            lines.append("  Result: FILTERED (not accessible to this knower)")
        elif document.id in ranked_by_id:
            lines.append(f"  Result: SELECTED (score = {ranked_by_id[document.id].score:.2f})")
        else:
            lines.append("  Result: FILTERED (outside ranking limit)")
        lines.append("")

    logger.debug("\n".join(lines))
