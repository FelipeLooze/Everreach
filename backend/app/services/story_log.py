import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models.event import WorldEvent


# Phase 24D — the conceptual speaker vocabulary. `kind` stays a plain
# string (matching the pre-existing field, and every caller that
# already compares it to "player"/"narrator" literally) rather than a
# new enum type — these constants just give that vocabulary a single
# documented home. "NPC" is deliberately NOT a fourth `kind` value:
# narrator.narrate() still returns one blended string per non-player
# turn (scene narration and any NPC dialogue together, never stored
# separately — that split is Phase 24G's job, not this one), so an NPC
# utterance is represented as kind=SPEAKER_NARRATOR with npc_id/npc_name
# populated, not as its own kind. SPEAKER_SYSTEM has no producer yet
# (no system-authored StoryEntry exists today) — reserved, not unused
# dead code, since 24D's own goal explicitly names it.
SPEAKER_PLAYER = "player"
SPEAKER_NARRATOR = "narrator"
SPEAKER_SYSTEM = "system"


@dataclass(frozen=True)
class StoryEntry:
    id: str
    kind: str
    text: str
    created_at: datetime
    # None for a player entry, for an event logged before Phase 24D, or
    # for a narrated turn with no active interlocutor (matching
    # engine.py's own context_npc resolution — the backend decided
    # this, the LLM was never asked).
    npc_id: str | None = None
    npc_name: str | None = None


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
                        kind=SPEAKER_NARRATOR,
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
                    kind=SPEAKER_PLAYER,
                    text=str(player_text),
                    created_at=event.created_at,
                )
            )
        if narrative:
            entries.append(
                StoryEntry(
                    id=f"{event.id}:narrator",
                    kind=SPEAKER_NARRATOR,
                    text=str(narrative),
                    created_at=event.created_at,
                    npc_id=payload.get("npc_id"),
                    npc_name=payload.get("npc_name"),
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
