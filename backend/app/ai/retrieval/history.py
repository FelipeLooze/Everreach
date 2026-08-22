"""Phase 18C — Historical Event Index.

Reuses app.services.event_log.EVENT_IMPORTANCE (the importance-per-
event-type table already assigning 1-5 significance to every EventType)
and app.ai.memory_manager.event_summary_text (the same prose generator
Memory rows already use) instead of inventing a second scoring/summary
system. A WorldEvent becomes a searchable historical document under the
exact same importance>=3 threshold app.ai.memory_manager.
remember_important_event already uses for perspective-bound Memory —
both exist to answer "what happened that matters", just from different
vantage points (Memory = who experienced it; this = campaign-wide
searchable history).
"""
import json

from sqlalchemy.orm import Session

from app.ai.memory_manager import event_summary_text
from app.ai.retrieval.documents import upsert_document
from app.core.enums import KnowledgeDocumentType, KnowledgeSourceType
from app.db.models.event import WorldEvent
from app.db.models.knowledge_index import IndexedKnowledgeDocument

HISTORICAL_EVENT_MIN_IMPORTANCE = 3


def index_historical_event(db: Session, event: WorldEvent) -> IndexedKnowledgeDocument | None:
    if event.importance < HISTORICAL_EVENT_MIN_IMPORTANCE:
        return None
    try:
        payload = json.loads(event.payload_json)
    except (json.JSONDecodeError, TypeError):
        payload = {}
    text = event_summary_text(db, event, payload)
    return upsert_document(
        db,
        event.campaign_id,
        KnowledgeSourceType.EVENT,
        event.id,
        KnowledgeDocumentType.HISTORICAL_EVENT,
        text,
        occurred_world_minute=event.world_minute,
        source_version=str(event.importance),
    )
