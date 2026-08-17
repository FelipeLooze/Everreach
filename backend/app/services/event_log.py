import json

from sqlalchemy.orm import Session

from app.core.enums import EventType
from app.db.models import WorldEvent
from app.db.models.campaign import WorldTime
from app.core.logging import get_logger

logger = get_logger("game")


EVENT_IMPORTANCE = {
    EventType.PLAYER_DIED: 5,
    EventType.BOSS_DEFEATED: 5,
    EventType.WORLD_STARTED: 4,
    EventType.PLAYER_LEVELED_UP: 4,
    EventType.QUEST_COMPLETED: 4,
    EventType.BOSS_DISCOVERED: 4,
    EventType.NEW_TECHNIQUE_CREATED: 4,
    EventType.PLAYER_MET_NPC: 3,
    EventType.PLAYER_MOVED: 3,
    EventType.LOCATION_DISCOVERED: 3,
    EventType.QUEST_STARTED: 3,
    EventType.KNOWLEDGE_PROPAGATED: 3,
    EventType.QUEST_OBJECTIVE_COMPLETED: 2,
    EventType.PLAYER_GAINED_XP: 2,
    EventType.ACTION_CHECK_RESULT: 2,
    EventType.PLAYER_RESTED: 1,
    EventType.STORY_EXCHANGE: 1,
}


def log_event(
    db: Session,
    campaign_id: str,
    event_type: EventType,
    actor_type: str = "",
    actor_id: str = "",
    payload: dict | None = None,
    importance: int | None = None,
) -> WorldEvent:
    world_time = db.query(WorldTime).filter(WorldTime.campaign_id == campaign_id).first()
    world_minute = world_time.total_minutes() if world_time else 0

    event = WorldEvent(
        campaign_id=campaign_id,
        event_type=event_type.value,
        actor_type=actor_type,
        actor_id=actor_id,
        payload_json=json.dumps(payload or {}),
        world_minute=world_minute,
        importance=max(1, min(5, importance or EVENT_IMPORTANCE.get(event_type, 1))),
    )
    db.add(event)
    db.flush()
    if event.importance >= 3:
        from app.ai.memory_manager import remember_important_event

        remember_important_event(db, event)
    logger.info("event %s campaign=%s actor=%s:%s", event_type.value, campaign_id, actor_type, actor_id)
    return event


def recent_events(
    db: Session,
    campaign_id: str,
    limit: int = 20,
    *,
    actor_id: str | None = None,
    min_importance: int | None = None,
) -> list[WorldEvent]:
    query = db.query(WorldEvent).filter(WorldEvent.campaign_id == campaign_id)
    if actor_id is not None:
        query = query.filter(WorldEvent.actor_id == actor_id)
    if min_importance is not None:
        query = query.filter(WorldEvent.importance >= min_importance)
    return (
        query
        .order_by(WorldEvent.created_at.desc())
        .limit(limit)
        .all()
    )
