import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.event import WorldEvent


@dataclass(frozen=True)
class StoryEntry:
    id: str
    kind: str
    text: str
    created_at: datetime


def _story_events_query(db: Session, campaign_id: str, character_id: str):
    return (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.actor_id == character_id,
            WorldEvent.event_type.in_((EventType.WORLD_STARTED, EventType.STORY_EXCHANGE)),
        )
    )


def _entries_from_events(events: list[WorldEvent]) -> list[StoryEntry]:
    entries: list[StoryEntry] = []
    for event in events:
        try:
            payload = json.loads(event.payload_json)
        except json.JSONDecodeError:
            continue

        if event.event_type == EventType.WORLD_STARTED:
            narrative = payload.get("narrative")
            if narrative:
                entries.append(
                    StoryEntry(
                        id=f"{event.id}:narrator",
                        kind="narrator",
                        text=str(narrative),
                        created_at=event.created_at,
                    )
                )
            continue

        player_text = payload.get("player_text")
        narrative = payload.get("narrative")
        if player_text:
            entries.append(
                StoryEntry(
                    id=f"{event.id}:player",
                    kind="player",
                    text=str(player_text),
                    created_at=event.created_at,
                )
            )
        if narrative:
            entries.append(
                StoryEntry(
                    id=f"{event.id}:narrator",
                    kind="narrator",
                    text=str(narrative),
                    created_at=event.created_at,
                )
            )

    return entries


def get_story_log(db: Session, campaign_id: str, character_id: str) -> list[StoryEntry]:
    events = (
        _story_events_query(db, campaign_id, character_id)
        .order_by(WorldEvent.created_at.asc(), WorldEvent.id.asc())
        .all()
    )
    return _entries_from_events(events)


def get_recent_story_log(
    db: Session,
    campaign_id: str,
    character_id: str,
    event_limit: int = 4,
) -> list[StoryEntry]:
    events = (
        _story_events_query(db, campaign_id, character_id)
        .order_by(WorldEvent.created_at.desc(), WorldEvent.id.desc())
        .limit(event_limit)
        .all()
    )
    events.reverse()
    return _entries_from_events(events)
