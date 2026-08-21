"""Phase 13F — Roles, Ranks & Permissions.

Roles are always scoped to one organization — never a shared global rank
list. A Hunter Guild's "Guildmaster" and a Church's "High Priest" are
unrelated OrganizationRole rows; a Community organization may have no
roles at all (role_id on OrganizationMember is nullable).

Permissions are stored as a JSON list drawn from OrganizationPermission's
vocabulary — nothing here enforces them yet (Phase 13K Organization
Actions and beyond will), so role_has_permission is a ready primitive,
not something wired into a hardcoded condition chain today.

A character or NPC may belong to multiple organizations — nothing here
restricts membership to one org at a time (see member_organizations).
"""

import json

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    EventType,
    OrganizationMembershipStatus,
    OrganizationPermission,
)
from app.db.models.organization import Organization, OrganizationMember, OrganizationRole
from app.game.organizations.service import OrganizationError
from app.game.time.clock import get_world_time
from app.services.event_log import log_event

_TERMINAL_STATUSES = (
    OrganizationMembershipStatus.EXPELLED,
    OrganizationMembershipStatus.LEFT,
    OrganizationMembershipStatus.DECEASED,
)


def create_role(
    db: Session,
    organization: Organization,
    title: str,
    *,
    rank_order: int = 0,
    permissions: tuple[OrganizationPermission, ...] = (),
) -> OrganizationRole:
    if not title.strip():
        raise OrganizationError("Um papel precisa de um título.")
    role = OrganizationRole(
        organization_id=organization.id,
        title=title,
        rank_order=rank_order,
        permissions_json=json.dumps(list(permissions)),
    )
    db.add(role)
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_ROLE_CREATED,
        actor_type="organization",
        actor_id=organization.id,
        payload={"role_id": role.id, "title": title},
    )
    return role


def role_has_permission(role: OrganizationRole | None, permission: OrganizationPermission) -> bool:
    if role is None:
        return False
    return permission in json.loads(role.permissions_json)


def _open_stint(
    db: Session, organization_id: str, member_type: CombatActorType, member_id: str
) -> OrganizationMember | None:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.member_type == member_type,
            OrganizationMember.member_id == member_id,
            OrganizationMember.status.in_(
                (OrganizationMembershipStatus.ACTIVE, OrganizationMembershipStatus.SUSPENDED)
            ),
        )
        .first()
    )


def join_organization(
    db: Session,
    organization: Organization,
    member_type: CombatActorType,
    member_id: str,
    *,
    role_id: str | None = None,
) -> OrganizationMember:
    if _open_stint(db, organization.id, member_type, member_id) is not None:
        raise OrganizationError("Este personagem já é membro desta organização.")
    if role_id is not None:
        role = db.get(OrganizationRole, role_id)
        if role is None or role.organization_id != organization.id:
            raise OrganizationError("Este papel não pertence a esta organização.")

    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    member = OrganizationMember(
        organization_id=organization.id,
        member_type=member_type,
        member_id=member_id,
        role_id=role_id,
        status=OrganizationMembershipStatus.ACTIVE,
        joined_world_minute=world_minute,
    )
    db.add(member)
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_MEMBER_JOINED,
        actor_type=member_type.lower(),
        actor_id=member_id,
        payload={"organization_id": organization.id, "role_id": role_id},
        occurred_world_minute=world_minute,
    )
    return member


def set_membership_status(
    db: Session, member: OrganizationMember, new_status: OrganizationMembershipStatus
) -> OrganizationMember:
    """Covers LEFT/SUSPENDED/EXPELLED/DECEASED/reinstated-to-ACTIVE
    uniformly — the spec lists these as concepts, not each demanding its
    own dedicated function. Reaching a terminal status stamps
    left_world_minute; the row itself is never deleted."""
    if member.status == new_status:
        return member
    organization = db.get(Organization, member.organization_id)
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    previous_status = member.status
    member.status = new_status
    if new_status in _TERMINAL_STATUSES:
        member.left_world_minute = world_minute
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_MEMBER_STATUS_CHANGED,
        actor_type=member.member_type.lower(),
        actor_id=member.member_id,
        payload={
            "organization_id": organization.id,
            "previous_status": previous_status,
            "new_status": new_status,
        },
        occurred_world_minute=world_minute,
    )
    return member


def change_member_role(
    db: Session, member: OrganizationMember, role_id: str | None
) -> OrganizationMember:
    """Covers promotion and demotion alike — both are just a role_id
    change; which direction it is depends on the two roles' rank_order,
    not on which function was called."""
    if role_id is not None:
        role = db.get(OrganizationRole, role_id)
        if role is None or role.organization_id != member.organization_id:
            raise OrganizationError("Este papel não pertence a esta organização.")
    organization = db.get(Organization, member.organization_id)
    world_minute = get_world_time(db, organization.campaign_id).total_minutes()
    previous_role_id = member.role_id
    member.role_id = role_id
    db.flush()

    log_event(
        db,
        organization.campaign_id,
        EventType.ORGANIZATION_MEMBER_ROLE_CHANGED,
        actor_type=member.member_type.lower(),
        actor_id=member.member_id,
        payload={
            "organization_id": organization.id,
            "previous_role_id": previous_role_id,
            "new_role_id": role_id,
        },
        occurred_world_minute=world_minute,
    )
    return member


def active_members(db: Session, organization_id: str) -> list[OrganizationMember]:
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .order_by(OrganizationMember.joined_world_minute)
        .all()
    )


def member_organizations(
    db: Session, member_type: CombatActorType, member_id: str
) -> list[OrganizationMember]:
    """Every organization this character/NPC currently actively belongs
    to — deliberately unrestricted to one. Multiple simultaneous
    memberships are a supported, expected case, not an edge case to
    guard against."""
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.member_type == member_type,
            OrganizationMember.member_id == member_id,
            OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
        )
        .all()
    )
