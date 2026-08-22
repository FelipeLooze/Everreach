"""Phase 13A — Group Foundation.

A Group can mix Character, NPC and SimulatedPlayer members (unlike
SimulatedPlayerGroup, which is simulated-player-only) and requires no
name, no leader, and no location. add_member/remove_member are bare
primitives here — no consent semantics; Phase 13B builds the
invite/accept/refuse flow on top.
"""

import pytest

from app.core.enums import CombatActorType, GroupStatus, GroupType
from app.game.character.service import create_character
from app.game.groups.service import (
    GroupError,
    active_group_for_member,
    active_group_members,
    add_member,
    create_group,
    disband_group,
    remove_member,
)
from app.game.world.seed import create_campaign, seed_initial_region
from app.db.models.npc import NPC


def _setup(db_session):
    campaign = create_campaign(db_session, "Group Foundation")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    db_session.flush()
    return campaign, region, village, character, osgar


def test_group_can_mix_character_and_npc_members(db_session):
    campaign, region, village, character, osgar = _setup(db_session)

    group = create_group(
        db_session, campaign.id,
        group_type=GroupType.TRAVEL,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
    )

    members = active_group_members(db_session, group.id)
    assert {(m.member_type, m.member_id) for m in members} == {
        (CombatActorType.CHARACTER, character.id),
        (CombatActorType.NPC, osgar.id),
    }


def test_group_needs_no_name_leader_or_location(db_session):
    campaign, region, village, character, osgar = _setup(db_session)

    group = create_group(
        db_session, campaign.id,
        group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )

    assert group.name is None
    assert group.leader_type is None
    assert group.leader_id is None
    assert group.location_id is None
    assert group.status == GroupStatus.ACTIVE


def test_a_group_requires_at_least_one_founding_member(db_session):
    campaign, region, village, character, osgar = _setup(db_session)

    with pytest.raises(GroupError):
        create_group(db_session, campaign.id, group_type=GroupType.TRAVEL, founding_members=[])


def test_active_group_for_member_finds_the_right_group(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id,
        group_type=GroupType.EXPEDITION,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )

    found = active_group_for_member(db_session, CombatActorType.CHARACTER, character.id)

    assert found is not None and found.id == group.id


def test_add_member_is_idempotent_and_reactivates_a_former_member(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id,
        group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )

    add_member(db_session, group, CombatActorType.NPC, osgar.id)
    remove_member(db_session, group, CombatActorType.NPC, osgar.id)
    add_member(db_session, group, CombatActorType.NPC, osgar.id)

    assert active_group_for_member(db_session, CombatActorType.NPC, osgar.id).id == group.id


def test_cannot_add_a_member_to_a_disbanded_group(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id,
        group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )
    disband_group(db_session, group)

    with pytest.raises(GroupError):
        add_member(db_session, group, CombatActorType.NPC, osgar.id)


def test_disbanding_deactivates_every_member(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id,
        group_type=GroupType.TRAVEL,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
    )

    disband_group(db_session, group)

    assert active_group_members(db_session, group.id) == []
    assert group.status == GroupStatus.DISBANDED


def test_removing_the_leader_promotes_the_next_active_member(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id,
        group_type=GroupType.TRAVEL,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
        leader_type=CombatActorType.CHARACTER,
        leader_id=character.id,
    )

    remove_member(db_session, group, CombatActorType.CHARACTER, character.id)

    assert group.leader_type == CombatActorType.NPC
    assert group.leader_id == osgar.id


def test_removing_the_last_member_leaves_no_leader(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id,
        group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
        leader_type=CombatActorType.CHARACTER,
        leader_id=character.id,
    )

    remove_member(db_session, group, CombatActorType.CHARACTER, character.id)

    assert group.leader_type is None
    assert group.leader_id is None
