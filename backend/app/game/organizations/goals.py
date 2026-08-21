"""Phase 13I — Organization Goals & Needs.

GOAL != NEED: a Goal is the qualitative reason an organization acts
("keep the northern trade route safe"); a Need is a concrete resource or
capability gap serving one, or standing alone ("more hunters", "arrows",
"information about wolf activity"). Needs are what Phase 13M will
eventually route toward Notices/jobs — nothing here builds that routing
or any autonomous strategy AI; priority exists purely as a persisted,
queryable hook for whatever evaluates it later.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    EventType,
    OrganizationGoalStatus,
    OrganizationNeedCategory,
    OrganizationNeedStatus,
)
from app.db.models.organization import Organization, OrganizationGoal, OrganizationNeed
from app.game.organizations.service import OrganizationError
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


def create_goal(
    db: Session, organization: Organization, description: str, *, priority: int = 0
) -> OrganizationGoal:
    if not description.strip():
        raise OrganizationError("Um objetivo precisa de uma descrição.")
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    goal = OrganizationGoal(
        organization_id=organization.id,
        description=description,
        status=OrganizationGoalStatus.ACTIVE,
        priority=priority,
        created_world_minute=world_minute,
    )
    db.add(goal)
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_GOAL_CREATED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"goal_id": goal.id, "description": description},
        occurred_world_minute=world_minute,
    )
    return goal


def set_goal_status(
    db: Session, goal: OrganizationGoal, new_status: OrganizationGoalStatus
) -> OrganizationGoal:
    if goal.status == new_status:
        return goal
    organization = db.get(Organization, goal.organization_id)
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    previous_status = goal.status
    goal.status = new_status
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_GOAL_STATUS_CHANGED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"goal_id": goal.id, "previous_status": previous_status, "new_status": new_status},
        occurred_world_minute=world_minute,
    )
    return goal


def create_need(
    db: Session,
    organization: Organization,
    description: str,
    *,
    category: OrganizationNeedCategory,
    priority: int = 0,
    goal_id: str | None = None,
) -> OrganizationNeed:
    if not description.strip():
        raise OrganizationError("Uma necessidade precisa de uma descrição.")
    if goal_id is not None:
        goal = db.get(OrganizationGoal, goal_id)
        if goal is None or goal.organization_id != organization.id:
            raise OrganizationError("Este objetivo não pertence a esta organização.")

    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    need = OrganizationNeed(
        organization_id=organization.id,
        goal_id=goal_id,
        category=category,
        description=description,
        status=OrganizationNeedStatus.OPEN,
        priority=priority,
        created_world_minute=world_minute,
    )
    db.add(need)
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_NEED_CREATED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"need_id": need.id, "category": category, "goal_id": goal_id},
        occurred_world_minute=world_minute,
    )
    return need


def set_need_status(
    db: Session, need: OrganizationNeed, new_status: OrganizationNeedStatus
) -> OrganizationNeed:
    if need.status == new_status:
        return need
    organization = db.get(Organization, need.organization_id)
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    previous_status = need.status
    need.status = new_status
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_NEED_STATUS_CHANGED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"need_id": need.id, "previous_status": previous_status, "new_status": new_status},
        occurred_world_minute=world_minute,
    )
    return need


def active_goals(db: Session, organization_id: str) -> list[OrganizationGoal]:
    return (
        db.query(OrganizationGoal)
        .filter(
            OrganizationGoal.organization_id == organization_id,
            OrganizationGoal.status == OrganizationGoalStatus.ACTIVE,
        )
        .order_by(OrganizationGoal.priority.desc(), OrganizationGoal.created_world_minute)
        .all()
    )


def open_needs(db: Session, organization_id: str) -> list[OrganizationNeed]:
    return (
        db.query(OrganizationNeed)
        .filter(
            OrganizationNeed.organization_id == organization_id,
            OrganizationNeed.status == OrganizationNeedStatus.OPEN,
        )
        .order_by(OrganizationNeed.priority.desc(), OrganizationNeed.created_world_minute)
        .all()
    )
