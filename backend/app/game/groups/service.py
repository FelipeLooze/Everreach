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

from app.core.enums import (
    CombatActorType,
    EventType,
    GroupInviteStatus,
    GroupStatus,
    GroupType,
)
from app.db.models.group import Group, GroupInvite, GroupMember
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


# ---------------------------------------------------------------------------
# Phase 13B — Group Membership & Temporary Groups.
#
# invite/accept/decline/withdraw are the agency-preserving layer: an
# invite is never assumed accepted. Someone proposing to travel together
# does not create membership by itself — only an explicit accept_invite
# call (by the invited party's own decision) does. Who actually makes
# that decision for an NPC (personality, relationship, current goals...)
# is not decided here — this module only guarantees the state machine
# itself can never be bypassed silently by narration.
# ---------------------------------------------------------------------------


def invite_to_group(
    db: Session,
    group: Group,
    *,
    inviter_type: CombatActorType,
    inviter_id: str,
    invited_type: CombatActorType,
    invited_id: str,
) -> GroupInvite:
    if group.status != GroupStatus.ACTIVE:
        raise GroupError(f"Não é possível convidar para um grupo com status {group.status}.")
    already_member = (
        db.query(GroupMember)
        .filter(
            GroupMember.group_id == group.id,
            GroupMember.member_type == invited_type,
            GroupMember.member_id == invited_id,
            GroupMember.active.is_(True),
        )
        .first()
    )
    if already_member is not None:
        raise GroupError("Este personagem já faz parte do grupo.")
    existing_pending = (
        db.query(GroupInvite)
        .filter(
            GroupInvite.group_id == group.id,
            GroupInvite.invited_type == invited_type,
            GroupInvite.invited_id == invited_id,
            GroupInvite.status == GroupInviteStatus.PENDING,
        )
        .first()
    )
    if existing_pending is not None:
        return existing_pending

    world_minute = get_world_time(db, group.campaign_id).total_minutes()
    invite = GroupInvite(
        group_id=group.id,
        inviter_type=inviter_type,
        inviter_id=inviter_id,
        invited_type=invited_type,
        invited_id=invited_id,
        status=GroupInviteStatus.PENDING,
        created_world_minute=world_minute,
    )
    db.add(invite)
    db.flush()

    log_event(
        db,
        group.campaign_id,
        EventType.GROUP_INVITE_SENT,
        actor_type=inviter_type.lower(),
        actor_id=inviter_id,
        payload={"group_id": group.id, "invited_type": invited_type, "invited_id": invited_id},
        occurred_world_minute=world_minute,
    )
    return invite


def _resolve_invite(
    db: Session, invite: GroupInvite, *, new_status: GroupInviteStatus, event_type: EventType
) -> GroupInvite:
    if invite.status != GroupInviteStatus.PENDING:
        raise GroupError(f"Este convite já não está mais pendente ({invite.status}).")
    group = db.get(Group, invite.group_id)
    world_minute = get_world_time(db, group.campaign_id).total_minutes()
    invite.status = new_status
    invite.resolved_world_minute = world_minute
    db.flush()
    log_event(
        db,
        group.campaign_id,
        event_type,
        actor_type=invite.invited_type.lower(),
        actor_id=invite.invited_id,
        payload={"group_id": group.id, "invite_id": invite.id},
        occurred_world_minute=world_minute,
    )
    return invite


def accept_invite(db: Session, invite: GroupInvite) -> GroupMember:
    """The invited party's own explicit decision — the only way an invite
    ever turns into real membership."""
    _resolve_invite(
        db, invite, new_status=GroupInviteStatus.ACCEPTED, event_type=EventType.GROUP_INVITE_ACCEPTED
    )
    group = db.get(Group, invite.group_id)
    return add_member(db, group, invite.invited_type, invite.invited_id)


def decline_invite(db: Session, invite: GroupInvite) -> GroupInvite:
    return _resolve_invite(
        db, invite, new_status=GroupInviteStatus.DECLINED, event_type=EventType.GROUP_INVITE_DECLINED
    )


def withdraw_invite(db: Session, invite: GroupInvite) -> GroupInvite:
    """The inviter rescinds before it was answered."""
    return _resolve_invite(
        db, invite, new_status=GroupInviteStatus.WITHDRAWN, event_type=EventType.GROUP_INVITE_WITHDRAWN
    )


def change_leader(
    db: Session, group: Group, *, new_leader_type: CombatActorType, new_leader_id: str
) -> Group:
    """Explicit leadership change — a Group may also have shared or no
    formal leadership (Phase 13A); this is only for when a change is
    itself a meaningful, deliberate act."""
    is_active_member = (
        db.query(GroupMember)
        .filter(
            GroupMember.group_id == group.id,
            GroupMember.member_type == new_leader_type,
            GroupMember.member_id == new_leader_id,
            GroupMember.active.is_(True),
        )
        .first()
        is not None
    )
    if not is_active_member:
        raise GroupError("O novo líder precisa ser um membro ativo do grupo.")

    world_minute = get_world_time(db, group.campaign_id).total_minutes()
    group.leader_type = new_leader_type
    group.leader_id = new_leader_id
    db.flush()
    log_event(
        db,
        group.campaign_id,
        EventType.GROUP_LEADERSHIP_CHANGED,
        actor_type="group",
        actor_id=group.id,
        payload={"new_leader_type": new_leader_type, "new_leader_id": new_leader_id},
        occurred_world_minute=world_minute,
    )
    return group
