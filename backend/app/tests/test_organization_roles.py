"""Phase 13F — Roles, Ranks & Permissions.

Roles are scoped to one organization each — no shared global rank list.
Membership is one row per stint, preserving an expulsion followed by a
later rejoin as two distinct historical facts. Characters and NPCs may
belong to multiple organizations at once.
"""

import pytest

from app.core.enums import (
    CombatActorType,
    OrganizationMembershipStatus,
    OrganizationOrigin,
    OrganizationPermission,
    OrganizationType,
)
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.organizations.roles import (
    active_members,
    change_member_role,
    create_role,
    join_organization,
    member_organizations,
    role_has_permission,
    set_membership_status,
)
from app.game.organizations.service import OrganizationError, create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Roles")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    db_session.flush()
    return campaign, region, village, character, osgar


def _org(db_session, campaign, name="Guilda dos Caçadores de Cardal"):
    return create_organization(
        db_session, campaign.id, name,
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )


def test_two_organizations_have_independent_role_sets(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    guild = _org(db_session, campaign, "Guilda dos Caçadores de Cardal")
    church = _org(db_session, campaign, "Templo de Cardal")

    guildmaster = create_role(db_session, guild, "Guildmaster", rank_order=0)
    high_priest = create_role(db_session, church, "Alto Sacerdote", rank_order=0)

    assert guildmaster.organization_id == guild.id
    assert high_priest.organization_id == church.id
    assert guildmaster.title != high_priest.title


def test_join_organization_without_a_role_is_allowed(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    community = _org(db_session, campaign, "Conselho da Vila")

    member = join_organization(db_session, community, CombatActorType.CHARACTER, character.id)

    assert member.role_id is None
    assert member.status == OrganizationMembershipStatus.ACTIVE


def test_cannot_join_the_same_organization_twice_while_active(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    guild = _org(db_session, campaign)
    join_organization(db_session, guild, CombatActorType.CHARACTER, character.id)

    with pytest.raises(OrganizationError):
        join_organization(db_session, guild, CombatActorType.CHARACTER, character.id)


def test_character_may_belong_to_multiple_organizations(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    guild = _org(db_session, campaign, "Guilda dos Caçadores de Cardal")
    church = _org(db_session, campaign, "Templo de Cardal")

    join_organization(db_session, guild, CombatActorType.CHARACTER, character.id)
    join_organization(db_session, church, CombatActorType.CHARACTER, character.id)

    memberships = member_organizations(db_session, CombatActorType.CHARACTER, character.id)
    assert {m.organization_id for m in memberships} == {guild.id, church.id}


def test_expulsion_then_rejoin_preserves_both_stints(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    guild = _org(db_session, campaign)
    first_stint = join_organization(db_session, guild, CombatActorType.NPC, osgar.id)
    set_membership_status(db_session, first_stint, OrganizationMembershipStatus.EXPELLED)

    second_stint = join_organization(db_session, guild, CombatActorType.NPC, osgar.id)

    assert first_stint.id != second_stint.id
    assert first_stint.status == OrganizationMembershipStatus.EXPELLED
    assert first_stint.left_world_minute is not None
    assert second_stint.status == OrganizationMembershipStatus.ACTIVE
    assert second_stint.left_world_minute is None


def test_active_members_excludes_suspended_and_expelled(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    guild = _org(db_session, campaign)
    active_one = join_organization(db_session, guild, CombatActorType.CHARACTER, character.id)
    suspended_one = join_organization(db_session, guild, CombatActorType.NPC, osgar.id)
    set_membership_status(db_session, suspended_one, OrganizationMembershipStatus.SUSPENDED)

    roster = active_members(db_session, guild.id)

    assert [m.id for m in roster] == [active_one.id]


def test_change_member_role_validates_the_role_belongs_to_the_organization(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    guild = _org(db_session, campaign, "Guilda dos Caçadores de Cardal")
    church = _org(db_session, campaign, "Templo de Cardal")
    foreign_role = create_role(db_session, church, "Acólito")
    member = join_organization(db_session, guild, CombatActorType.CHARACTER, character.id)

    with pytest.raises(OrganizationError):
        change_member_role(db_session, member, foreign_role.id)


def test_promotion_updates_the_members_role(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    guild = _org(db_session, campaign)
    apprentice = create_role(db_session, guild, "Aprendiz", rank_order=3)
    hunter = create_role(db_session, guild, "Caçador", rank_order=2)
    member = join_organization(
        db_session, guild, CombatActorType.CHARACTER, character.id, role_id=apprentice.id
    )

    change_member_role(db_session, member, hunter.id)

    assert member.role_id == hunter.id


def test_role_permissions_are_stored_and_queryable(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    guild = _org(db_session, campaign)
    guildmaster = create_role(
        db_session, guild, "Guildmaster",
        permissions=(OrganizationPermission.RECRUIT_MEMBER, OrganizationPermission.MANAGE_MONEY),
    )
    apprentice = create_role(db_session, guild, "Aprendiz")

    assert role_has_permission(guildmaster, OrganizationPermission.RECRUIT_MEMBER) is True
    assert role_has_permission(guildmaster, OrganizationPermission.CREATE_CONTRACT) is False
    assert role_has_permission(apprentice, OrganizationPermission.RECRUIT_MEMBER) is False
    assert role_has_permission(None, OrganizationPermission.RECRUIT_MEMBER) is False
