"""Phase 18L — Context Budget & Compression.

Applies only to the OPTIONAL retrieved-knowledge tail of a prompt
(spec's priority levels 8-10: retrieved long-term memory, relevant
history, background lore). Mandatory authoritative state (current
scene, actor identity, knowledge restrictions...) is direct database
context built by app.ai.context_builder and is never part of this
budget or subject to being dropped by it — that ordering is enforced by
construction (Phase 18N wires this module's output in only after the
mandatory sections), not by anything in here.

Compression strategy, in the spec's own preferred order:
1. ranking — already done by Phase 18K before this module ever runs.
2. deduplication — the same document reached via two ranked lists
   (e.g. one per document_type "section") is only counted/included once.
3. summaries — Phase 18E's memory consolidation already produces
   compact long-term documents upstream; this module does not
   re-summarize at retrieval time.
4. removal of redundant facts — out of scope for this subphase (no
   duplicate-meaning detection exists yet); documented, not hidden.

Never truncate randomly: once the budget is exhausted, only the lowest-
ranked remainder is dropped — the included set is always a PREFIX of
the ranked list, never a best-fit shuffle that could seat a lower-
ranked item ahead of a higher-ranked one that didn't fit.
"""
from dataclasses import dataclass

from app.ai.retrieval.ranking import RankedDocument
from app.core.enums import KnowledgeDocumentType

DEFAULT_CONTEXT_CHAR_BUDGET = 4000

_SECTION_LABELS = {
    KnowledgeDocumentType.IDENTITY: "RELEVANT IDENTITY",
    KnowledgeDocumentType.CURRENT_STATE: "RELEVANT CURRENT STATE",
    KnowledgeDocumentType.BACKGROUND: "RELEVANT BACKGROUND",
    KnowledgeDocumentType.IMPORTANT_HISTORY: "RELEVANT LONG-TERM MEMORY",
    KnowledgeDocumentType.RELATIONSHIP: "RELEVANT RELATIONSHIP CONTEXT",
    KnowledgeDocumentType.GEOGRAPHY: "RELEVANT GEOGRAPHY",
    KnowledgeDocumentType.ORGANIZATION_CONTEXT: "RELEVANT ORGANIZATION CONTEXT",
    KnowledgeDocumentType.HISTORICAL_EVENT: "RELEVANT WORLD HISTORY",
}


@dataclass(frozen=True)
class BudgetResult:
    included: list[RankedDocument]
    dropped_count: int
    used_chars: int


def fit_to_budget(
    ranked_documents: list[RankedDocument],
    *,
    max_chars: int = DEFAULT_CONTEXT_CHAR_BUDGET,
) -> BudgetResult:
    """ranked_documents must already be sorted best-first (Phase 18K's
    output order) — this function trusts that order and never re-ranks."""
    seen_ids: set[str] = set()
    included: list[RankedDocument] = []
    used_chars = 0
    for ranked in ranked_documents:
        if ranked.document.id in seen_ids:
            continue
        cost = len(ranked.document.text)
        if used_chars + cost > max_chars:
            break
        seen_ids.add(ranked.document.id)
        included.append(ranked)
        used_chars += cost
    return BudgetResult(
        included=included,
        dropped_count=len(ranked_documents) - len(included),
        used_chars=used_chars,
    )


def format_ranked_documents(ranked_documents: list[RankedDocument]) -> str:
    """Structured, labeled sections — never an unlabelled concatenated
    blob (spec's explicit instruction)."""
    grouped: dict[str, list[str]] = {}
    for ranked in ranked_documents:
        document_type = KnowledgeDocumentType(ranked.document.document_type)
        label = _SECTION_LABELS.get(document_type, document_type.value)
        grouped.setdefault(label, []).append(ranked.document.text)

    sections = []
    for label, texts in grouped.items():
        lines = [label, *[f"- {text}" for text in texts]]
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
