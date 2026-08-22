"""Phase 18E — Character & NPC Long-Term Memory (consolidation).

Memory (app.ai.memory_manager) already IS the perspective-bound episodic
layer — this subphase adds exactly one thing on top of it: once an
owner/subject pair has accumulated enough small episodes to be worth
compressing (spec's own example: "40 individual ordinary conversations
between Logan and Osgar"), fold them into one durable, retrievable
IndexedKnowledgeDocument instead of expecting every future prompt to
re-read dozens of raw Memory rows.

Deliberately NOT an LLM summarization pipeline (avoids a fifth LLM
consumer just for this, and "do not require constant LLM summarization
after every small interaction" per spec) — the count, the importance
trend, and the earliest/most-recent episode text already carry the
signal a consolidated document needs. Deliberately NOT automatic on
every remember_dialogue/remember_important_event call either — batching
by threshold, invoked explicitly by a caller once accumulation is worth
summarizing (Phase 18M wires this to real triggers), never per-turn.

Consolidation never deletes or rewrites the underlying Memory rows —
that raw history stays exactly as authoritative as it always was. The
IndexedKnowledgeDocument is retrieval assistance, not a replacement.
"""
from sqlalchemy.orm import Session

from app.ai.memory_manager import memories_for_subject
from app.ai.retrieval.documents import upsert_document
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType, MemoryOwnerType
from app.db.models.knowledge_index import IndexedKnowledgeDocument

CONSOLIDATION_MEMORY_THRESHOLD = 10

_OWNER_TO_SOURCE_TYPE = {
    MemoryOwnerType.PLAYER: KnowledgeSourceType.CHARACTER,
    MemoryOwnerType.NPC: KnowledgeSourceType.NPC,
    MemoryOwnerType.SIMULATED_PLAYER: KnowledgeSourceType.SIMULATED_PLAYER,
}


def consolidate_memories(
    db: Session,
    campaign_id: str,
    owner_type: MemoryOwnerType,
    owner_id: str,
    subject: str,
) -> IndexedKnowledgeDocument | None:
    """Returns None (does nothing) below the threshold — not every owner/
    subject pair needs or gets a long-term summary, only ones with
    enough accumulated history to compress. WORLD-owned memories are
    never consolidated (no KnowledgeSourceType maps to them; they are
    already campaign-wide, not perspective-bound in the way this exists
    to compress)."""
    source_type = _OWNER_TO_SOURCE_TYPE.get(owner_type)
    if source_type is None:
        return None

    memories = memories_for_subject(db, campaign_id, owner_type, owner_id, subject)
    if len(memories) < CONSOLIDATION_MEMORY_THRESHOLD:
        return None

    count = len(memories)
    average_importance = sum(memory.importance for memory in memories) / count
    first, last = memories[0], memories[-1]
    text = (
        f"Resumo de longo prazo ({count} interações registradas relacionadas a {subject}). "
        f"Primeira lembrança: {first.summary_text} "
        f"Lembrança mais recente: {last.summary_text} "
        f"Importância média: {average_importance:.1f}."
    )
    return upsert_document(
        db,
        campaign_id,
        source_type,
        f"{owner_id}:{subject}",
        KnowledgeDocumentType.IMPORTANT_HISTORY,
        text,
        occurred_world_minute=None,
        source_version=str(count),
    )
