"""Phase 13A — Group Foundation.

Low-level primitives only: a Group's roster can change through
add_member/remove_member, but whether that change represents a freely
given social decision (an NPC actually agreeing to travel together, the
protagonist actually accepting an invite) is the caller's responsibility
— Phase 13B builds the invite/accept/refuse flow that preserves player
and NPC agency on top of these. Nothing here assumes consent.

member_type reuses CombatActorType (CHARACTER/NPC/SIMULATED_PLAYER) — the
same "what kind of living actor" vocabulary CombatParticipant already
uses, rather than a new enum for the same concept.
"""

from typing import Sequence

from sqlalchemy.orm import Session

from app.core.enums import CombatActorType, EventType, GroupStatus, GroupType
from app.db.models.group import Group, GroupMember
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


class GroupError(Exception):
    pass


def create_group(
    db: Session,
    campaign_id: str,
    *,
    group_type: GroupType,
    founding_members: Sequence[tuple[CombatActorType, str]],
    name: str | None = None,
    purpose: str = "",
    location_id: str | None = None,
    leader_type: CombatActorType | None = None,
    leader_id: str | None = None,
) -> Group:
    if not founding_members:
        raise GroupError("Um grupo precisa de pelo menos um membro fundador.")
    world_minute = get_world_time(db, campaign_id).total_minutes()

    group = Group(
        campaign_id=campaign_id,
        name=name,
        group_type=group_type,
        purpose=purpose,
        status=GroupStatus.ACTIVE,
        leader_type=leader_type,
        leader_id=leader_id,
        location_id=location_id,
        created_world_minute=world_minute,
    )
    db.add(group)
    db.flush()

    for member_type, member_id in founding_members:
        db.add(
            GroupMember(
                group_id=group.id,
                member_type=member_type,
                member_id=member_id,
                joined_world_minute=world_minute,
                active=True,
            )
        )
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.GROUP_CREATED,
        actor_type="group",
        actor_id=group.id,
        payload={
            "group_type": group_type,
            "member_ids": [member_id for _type, member_id in founding_members],
        },
        occurred_world_minute=world_minute,
    )
    return group


def active_group_members(db: Session, group_id: str) -> list[GroupMember]:
    return (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.active.is_(True))
        .order_by(GroupMember.joined_world_minute)
        .all()
    )


def active_group_for_member(db: Session, member_type: CombatActorType, member_id: str) -> Group | None:
    return (
        db.query(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .filter(
            GroupMember.member_type == member_type,
            GroupMember.member_id == member_id,
            GroupMember.active.is_(True),
            Group.status == GroupStatus.ACTIVE,
        )
        .first()
    )


def add_member(
    db: Session,
    group: Group,
    member_type: CombatActorType,
    member_id: str,
) -> GroupMember:
    if group.status != GroupStatus.ACTIVE:
        raise GroupError(f"Não é possível entrar em um grupo com status {group.status}.")
    world_minute = get_world_time(db, group.campaign_id).total_minutes()

    membership = (
        db.query(GroupMember)
        .filter(
            GroupMember.group_id == group.id,
            GroupMember.member_type == member_type,
            GroupMember.member_id == member_id,
        )
        .first()
    )
    if membership is not None and membership.active:
        return membership
    if membership is None:
        membership = GroupMember(
            group_id=group.id,
            member_type=member_type,
            member_id=member_id,
            joined_world_minute=world_minute,
            active=True,
        )
        db.add(membership)
    else:
        membership.active = True
        membership.joined_world_minute = world_minute
        membership.left_world_minute = None
    db.flush()

    log_event(
        db,
        group.campaign_id,
        EventType.GROUP_MEMBER_JOINED,
        actor_type=member_type.lower(),
        actor_id=member_id,
        payload={"group_id": group.id},
        occurred_world_minute=world_minute,
    )
    return membership


def remove_member(db: Session, group: Group, member_type: CombatActorType, member_id: str) -> None:
    membership = (
        db.query(GroupMember)
        .filter(
            GroupMember.group_id == group.id,
            GroupMember.member_type == member_type,
            GroupMember.member_id == member_id,
            GroupMember.active.is_(True),
        )
        .first()
    )
    if membership is None:
        return
    world_minute = get_world_time(db, group.campaign_id).total_minutes()
    membership.active = False
    membership.left_world_minute = world_minute
    db.flush()

    log_event(
        db,
        group.campaign_id,
        EventType.GROUP_MEMBER_LEFT,
        actor_type=member_type.lower(),
        actor_id=member_id,
        payload={"group_id": group.id},
        occurred_world_minute=world_minute,
    )

    if group.leader_type == member_type and group.leader_id == member_id:
        remaining = active_group_members(db, group.id)
        if remaining:
            group.leader_type = remaining[0].member_type
            group.leader_id = remaining[0].member_id
        else:
            group.leader_type = None
            group.leader_id = None
        db.flush()


def disband_group(db: Session, group: Group) -> Group:
    if group.status != GroupStatus.ACTIVE:
        return group
    world_minute = get_world_time(db, group.campaign_id).total_minutes()
    for membership in active_group_members(db, group.id):
        membership.active = False
        membership.left_world_minute = world_minute
    group.status = GroupStatus.DISBANDED
    db.flush()

    log_event(
        db,
        group.campaign_id,
        EventType.GROUP_DISBANDED,
        actor_type="group",
        actor_id=group.id,
        payload={},
        occurred_world_minute=world_minute,
    )
    return group
