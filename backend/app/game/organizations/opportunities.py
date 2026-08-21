"""Phase 13M — Quest / Notice Integration.

Organizations become a real source of opportunities WITHOUT bypassing or
duplicating Phase 12's authority over quests/objectives/notices/
participation. publish_organization_notice calls Phase 12I's post_notice
directly; sponsor_quest calls Phase 12A's create_quest directly with
QuestSource.ORGANIZATION_REQUEST — the value Phase 12A already reserved
for exactly this case, before Organizations existed to fill it.

Neither function generates a posting or a quest merely because the
organization exists — both require the caller to have a real reason
(an open Need, in the common case) and both leave an OrganizationAction
audit trail (Phase 13K), which is the actual evidence a real
organizational decision produced this, not a random generator.
"""

from sqlalchemy.orm import Session

from app.core.enums import NoticeCategory, OrganizationActionType, QuestSource
from app.db.models.notice import Notice
from app.db.models.organization import Organization, OrganizationNeed
from app.db.models.quest import Quest
from app.game.notices.service import post_notice
from app.game.organizations.actions import record_organization_action
from app.game.organizations.service import OrganizationError
from app.game.quests.service import create_quest


def publish_organization_notice(
    db: Session,
    organization: Organization,
    board_feature_id: str,
    *,
    category: NoticeCategory,
    title: str,
    text: str,
    need_id: str | None = None,
    expires_world_minute: int | None = None,
) -> Notice:
    if need_id is not None:
        need = db.get(OrganizationNeed, need_id)
        if need is None or need.organization_id != organization.id:
            raise OrganizationError("Esta necessidade não pertence a esta organização.")

    notice = post_notice(
        db,
        organization.campaign_id,
        board_feature_id,
        category=category,
        title=title,
        text=text,
        expires_world_minute=expires_world_minute,
    )
    notice.author_organization_id = organization.id
    db.flush()

    record_organization_action(
        db, organization, OrganizationActionType.PUBLISH_NOTICE, f"Publicou aviso: {title}",
    )
    return notice


def sponsor_quest(
    db: Session,
    organization: Organization,
    region_id: str,
    name: str,
    description: str = "",
    *,
    objectives: tuple[str, ...] = (),
    deadline_world_minute: int | None = None,
) -> Quest:
    quest = create_quest(
        db,
        region_id,
        name,
        description,
        source=QuestSource.ORGANIZATION_REQUEST,
        objectives=objectives,
        deadline_world_minute=deadline_world_minute,
    )
    quest.sponsoring_organization_id = organization.id
    db.flush()

    record_organization_action(
        db, organization, OrganizationActionType.OTHER, f"Patrocinou a missão: {name}",
    )
    return quest
