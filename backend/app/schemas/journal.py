from datetime import datetime

from pydantic import BaseModel


class JournalEvent(BaseModel):
    id: str
    event_type: str
    actor_type: str
    actor_id: str
    world_minute: int
    importance: int
    payload: dict
    created_at: datetime


class JournalMemory(BaseModel):
    id: str
    subject: str
    summary_text: str
    importance: int
    source_event_id: str | None
    created_at: datetime


class JournalResponse(BaseModel):
    events: list[JournalEvent]
    memories: list[JournalMemory]
