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
    EventType.TRAVEL_INCIDENT: 2,
    EventType.LOCATION_DISCOVERED: 3,
    EventType.LOCATION_VISITED: 2,
    EventType.CONNECTION_DISCOVERED: 2,
    EventType.QUEST_STARTED: 3,
    EventType.QUEST_FAILED: 3,
    EventType.QUEST_RESOLVED_EXTERNALLY: 3,
    EventType.QUEST_CANCELLED: 2,
    EventType.QUEST_EXPIRED: 2,
    EventType.NOTICE_POSTED: 2,
    EventType.NOTICE_WITHDRAWN: 1,
    EventType.NOTICE_EXPIRED: 1,
    EventType.NOTICE_UPDATED: 1,
    EventType.GROUP_CREATED: 2,
    EventType.GROUP_MEMBER_JOINED: 1,
    EventType.GROUP_MEMBER_LEFT: 1,
    EventType.GROUP_DISBANDED: 2,
    EventType.GROUP_INVITE_SENT: 1,
    EventType.GROUP_INVITE_ACCEPTED: 2,
    EventType.GROUP_INVITE_DECLINED: 1,
    EventType.GROUP_INVITE_WITHDRAWN: 1,
    EventType.GROUP_LEADERSHIP_CHANGED: 2,
    EventType.ORGANIZATION_CREATED: 3,
    EventType.ORGANIZATION_STATUS_CHANGED: 3,
    EventType.ORGANIZATION_FOUNDED_FROM_GROUP: 3,
    EventType.ORGANIZATION_FORMALLY_RECOGNIZED: 2,
    EventType.ORGANIZATION_ROLE_CREATED: 1,
    EventType.ORGANIZATION_MEMBER_JOINED: 2,
    EventType.ORGANIZATION_MEMBER_STATUS_CHANGED: 2,
    EventType.ORGANIZATION_MEMBER_ROLE_CHANGED: 2,
    EventType.ORGANIZATION_REPUTATION_CHANGED: 2,
    EventType.ORGANIZATION_RELATION_ESTABLISHED: 3,
    EventType.ORGANIZATION_RELATION_ENDED: 3,
    EventType.ORGANIZATION_GOAL_CREATED: 2,
    EventType.ORGANIZATION_GOAL_STATUS_CHANGED: 2,
    EventType.ORGANIZATION_NEED_CREATED: 2,
    EventType.ORGANIZATION_NEED_STATUS_CHANGED: 1,
    EventType.ORGANIZATION_ASSET_ASSIGNED: 2,
    EventType.ORGANIZATION_ASSET_UNASSIGNED: 1,
    EventType.ORGANIZATION_FUNDS_CHANGED: 2,
    EventType.ORGANIZATION_ACTION_RESOLVED: 3,
    EventType.ORGANIZATION_CONFLICT_STARTED: 4,
    EventType.ORGANIZATION_CONFLICT_STATUS_CHANGED: 3,
    EventType.CURRENCY_DEPOSITED: 1,
    EventType.CURRENCY_WITHDRAWN: 1,
    EventType.CURRENCY_TRANSFERRED: 2,
    EventType.TRANSACTION_COMPLETED: 2,
    EventType.JOB_CREATED: 2,
    EventType.JOB_APPLICATION_SUBMITTED: 1,
    EventType.JOB_APPLICATION_RESOLVED: 2,
    EventType.JOB_EMPLOYMENT_ENDED: 2,
    EventType.WAGE_PAID: 2,
    EventType.PRODUCTION_COMPLETED: 2,
    EventType.SHOP_STOCKED: 1,
    EventType.SHOP_UNSTOCKED: 1,
    EventType.SHOP_TILL_CHANGED: 1,
    EventType.SUPPLY_CHANGED: 2,
    EventType.KNOWLEDGE_PROPAGATED: 3,
    EventType.QUEST_OBJECTIVE_COMPLETED: 2,
    EventType.PLAYER_GAINED_XP: 2,
    EventType.PLAYER_GAINED_PROFESSION_XP: 2,
    EventType.PLAYER_PROFESSION_LEVELED_UP: 4,
    EventType.PLAYER_COMPLETED_PROFESSION_ACTIVITY: 1,
    EventType.PLAYER_CLASS_OFFERED: 3,
    EventType.PLAYER_CLASS_OFFER_DELAYED: 1,
    EventType.PLAYER_CLASS_ACCEPTED: 4,
    EventType.PLAYER_ATTRIBUTE_INCREASED: 3,
    EventType.PLAYER_RESOURCE_MAX_INCREASED: 3,
    EventType.ACTION_CHECK_RESULT: 2,
    EventType.COMBAT_STARTED: 3,
    EventType.COMBAT_PARTICIPANT_JOINED: 2,
    EventType.COMBAT_PARTICIPANT_LEFT: 2,
    EventType.COMBAT_INITIATIVE_ROLLED: 2,
    EventType.COMBAT_TURN_ADVANCED: 1,
    EventType.COMBAT_ACTION_RESOLVED: 2,
    EventType.COMBAT_DAMAGE_APPLIED: 3,
    EventType.COMBAT_PARTICIPANT_INCAPACITATED: 4,
    EventType.COMBAT_CRITICAL_CHECK_RESOLVED: 2,
    EventType.COMBAT_PARTICIPANT_STABILIZED: 3,
    EventType.COMBAT_PARTICIPANT_RECOVERED: 3,
    EventType.COMBAT_RESOURCE_SPENT: 1,
    EventType.COMBAT_CONDITION_APPLIED: 2,
    EventType.COMBAT_CONDITION_TRIGGERED: 2,
    EventType.COMBAT_CONDITION_EXPIRED: 1,
    EventType.COMBAT_CONDITION_REMOVED: 1,
    EventType.COMBAT_TACTICAL_ACTION_RESOLVED: 2,
    EventType.COMBAT_AUTONOMOUS_DECISION_RESOLVED: 2,
    EventType.COMBAT_ENDED: 3,
    EventType.PLAYER_RESTED: 1,
    EventType.STORY_EXCHANGE: 1,
    EventType.WORLD_DEVELOPMENT_CREATED: 1,
    EventType.WORLD_DEVELOPMENT_UPDATED: 1,
    EventType.WORLD_DEVELOPMENT_COMPLETED: 2,
    EventType.SOCIAL_KNOWLEDGE_OPPORTUNITY_RESOLVED: 1,
    EventType.SIMULATED_PLAYER_DIED: 5,
    EventType.SIMULATED_PLAYER_LEVELED_UP: 4,
    EventType.SIMULATED_PLAYER_GAINED_XP: 2,
    EventType.SIMULATED_PLAYER_GOAL_COMPLETED: 2,
    EventType.SIMULATED_PLAYER_GOAL_ASSIGNED: 1,
    EventType.SIMULATED_PLAYER_GROUP_CREATED: 3,
    EventType.SIMULATED_PLAYER_GROUP_JOINED: 2,
    EventType.SIMULATED_PLAYER_GROUP_LEFT: 2,
    EventType.SIMULATED_PLAYER_GROUP_DISSOLVED: 3,
    EventType.SIMULATED_PLAYER_GROUP_TRAVEL_STARTED: 2,

}


def log_event(
    db: Session,
    campaign_id: str,
    event_type: EventType,
    actor_type: str = "",
    actor_id: str = "",
    payload: dict | None = None,
    importance: int | None = None,
    occurred_world_minute: int | None = None,
) -> WorldEvent:

    if occurred_world_minute is None:
        world_time = (
            db.query(WorldTime)
            .filter(
                WorldTime.campaign_id == campaign_id
            )
            .first()
        )

        world_minute = (
            world_time.total_minutes()
            if world_time
            else 0
        )
    else:
        world_minute = occurred_world_minute

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
        .order_by(
            WorldEvent.world_minute.desc(),
            WorldEvent.created_at.desc(),
            WorldEvent.id.desc(),
        )
        .limit(limit)
        .all()
    )
