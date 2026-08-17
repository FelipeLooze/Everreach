import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.memory_manager import get_owner_memories
from app.core.enums import MemoryOwnerType
from app.db.database import get_db
from app.db.models.campaign import Campaign
from app.db.models.character import Character
from app.schemas.journal import JournalEvent, JournalMemory, JournalResponse
from app.services.event_log import recent_events

router = APIRouter(prefix="/api/campaigns", tags=["journal"])


def _event_payload(payload_json: str) -> dict:
    try:
        payload = json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return {}

    return payload if isinstance(payload, dict) else {}


@router.get("/{campaign_id}/journal", response_model=JournalResponse)
def get_journal(
    campaign_id: str,
    character_id: str | None = None,
    db: Session = Depends(get_db),
):
    if db.get(Campaign, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    character = db.get(Character, character_id) if character_id else None
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")

    events = recent_events(db, campaign_id, limit=50, actor_id=character.id)
    memories = get_owner_memories(
        db, campaign_id, MemoryOwnerType.PLAYER, character.id, limit=50
    )
    return JournalResponse(
        events=[
            JournalEvent(
                id=event.id,
                event_type=event.event_type,
                actor_type=event.actor_type,
                actor_id=event.actor_id,
                world_minute=event.world_minute,
                importance=event.importance,
                payload=_event_payload(event.payload_json),
                created_at=event.created_at,
            )
            for event in events
        ],
        memories=[
            JournalMemory(
                id=memory.id,
                subject=memory.subject,
                summary_text=memory.summary_text,
                importance=memory.importance,
                source_event_id=memory.source_event_id,
                created_at=memory.created_at,
            )
            for memory in memories
        ],
    )
