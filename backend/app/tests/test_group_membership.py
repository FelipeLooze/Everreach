"""Phase 13B — Group Membership & Temporary Groups.

An invite is never assumed accepted. Sending one does not create
membership — only the invited party's own accept_invite call does.
Membership changes (join/leave/leadership) are always authoritative
events, never silent narration side effects.
"""

import pytest

from app.core.enums import CombatActorType, GroupInviteStatus, GroupType
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.groups.service import (
    GroupError,
    accept_invite,
    active_group_for_member,
    change_leader,
    create_group,
    decline_invite,
    invite_to_group,
    withdraw_invite,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Group Membership")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    mira = db_session.query(NPC).filter(NPC.name == "Mira Draske").first()
    db_session.flush()
    return campaign, region, village, character, osgar, mira


def test_sending_an_invite_does_not_create_membership(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )

    invite_to_group(
        db_session, group,
        inviter_type=CombatActorType.CHARACTER, inviter_id=character.id,
        invited_type=CombatActorType.NPC, invited_id=osgar.id,
    )

    assert active_group_for_member(db_session, CombatActorType.NPC, osgar.id) is None


def test_accepting_an_invite_creates_membership(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )
    invite = invite_to_group(
        db_session, group,
        inviter_type=CombatActorType.CHARACTER, inviter_id=character.id,
        invited_type=CombatActorType.NPC, invited_id=osgar.id,
    )

    membership = accept_invite(db_session, invite)

    assert membership.member_id == osgar.id
    assert active_group_for_member(db_session, CombatActorType.NPC, osgar.id).id == group.id
    assert invite.status == GroupInviteStatus.ACCEPTED


def test_declining_an_invite_leaves_the_npc_free(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )
    invite = invite_to_group(
        db_session, group,
        inviter_type=CombatActorType.CHARACTER, inviter_id=character.id,
        invited_type=CombatActorType.NPC, invited_id=osgar.id,
    )

    decline_invite(db_session, invite)

    assert invite.status == GroupInviteStatus.DECLINED
    assert active_group_for_member(db_session, CombatActorType.NPC, osgar.id) is None


def test_cannot_resolve_an_already_resolved_invite(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )
    invite = invite_to_group(
        db_session, group,
        inviter_type=CombatActorType.CHARACTER, inviter_id=character.id,
        invited_type=CombatActorType.NPC, invited_id=osgar.id,
    )
    decline_invite(db_session, invite)

    with pytest.raises(GroupError):
        accept_invite(db_session, invite)


def test_inviter_can_withdraw_a_pending_invite(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )
    invite = invite_to_group(
        db_session, group,
        inviter_type=CombatActorType.CHARACTER, inviter_id=character.id,
        invited_type=CombatActorType.NPC, invited_id=osgar.id,
    )

    withdraw_invite(db_session, invite)

    assert invite.status == GroupInviteStatus.WITHDRAWN
    with pytest.raises(GroupError):
        accept_invite(db_session, invite)


def test_cannot_invite_someone_already_a_member(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
    )

    with pytest.raises(GroupError):
        invite_to_group(
            db_session, group,
            inviter_type=CombatActorType.CHARACTER, inviter_id=character.id,
            invited_type=CombatActorType.NPC, invited_id=osgar.id,
        )


def test_inviting_the_same_person_twice_returns_the_same_pending_invite(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )

    first = invite_to_group(
        db_session, group,
        inviter_type=CombatActorType.CHARACTER, inviter_id=character.id,
        invited_type=CombatActorType.NPC, invited_id=osgar.id,
    )
    second = invite_to_group(
        db_session, group,
        inviter_type=CombatActorType.CHARACTER, inviter_id=character.id,
        invited_type=CombatActorType.NPC, invited_id=osgar.id,
    )

    assert first.id == second.id


def test_change_leader_requires_an_active_member(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )

    with pytest.raises(GroupError):
        change_leader(db_session, group, new_leader_type=CombatActorType.NPC, new_leader_id=mira.id)


def test_change_leader_updates_the_group(db_session):
    campaign, region, village, character, osgar, mira = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
        leader_type=CombatActorType.CHARACTER, leader_id=character.id,
    )

    change_leader(db_session, group, new_leader_type=CombatActorType.NPC, new_leader_id=osgar.id)

    assert group.leader_type == CombatActorType.NPC
    assert group.leader_id == osgar.id
