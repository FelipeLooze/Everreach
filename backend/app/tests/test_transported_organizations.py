"""Phase 13E — Transported-Created Organizations.

No "CREATE GUILD" button — an organization only comes from
found_organization_from_group, which requires a real, active Group with
at least two actually-agreed members (Phase 13A/13B's agency-preserving
roster, not a single character declaring it). The result is always
INFORMAL; formal recognition is a separate, later, explicit step.
"""

import pytest

from app.core.enums import (
    CombatActorType,
    GroupStatus,
    GroupType,
    OrganizationFormality,
    OrganizationOrigin,
    OrganizationType,
)
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.groups.service import create_group
from app.game.organizations.service import OrganizationError
from app.game.organizations.transported import (
    formally_recognize_organization,
    found_organization_from_group,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Transported Organizations")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    db_session.flush()
    return campaign, region, village, character, osgar


def test_founding_from_a_two_member_group_succeeds(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TEMPORARY_ALLIANCE,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
        leader_type=CombatActorType.CHARACTER, leader_id=character.id,
    )

    org = found_organization_from_group(
        db_session, group, "Os Andarilhos", organization_type=OrganizationType.COMMUNITY,
    )

    assert org.origin == OrganizationOrigin.TRANSPORTED_CREATED
    assert org.formality == OrganizationFormality.INFORMAL
    assert org.founder_type == CombatActorType.CHARACTER
    assert org.founder_id == character.id
    assert org.founding_group_id == group.id


def test_founding_from_a_solo_group_is_rejected(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[(CombatActorType.CHARACTER, character.id)],
    )

    with pytest.raises(OrganizationError):
        found_organization_from_group(
            db_session, group, "Bando de Um Só", organization_type=OrganizationType.COMMUNITY,
        )


def test_founding_from_a_dissolved_group_is_rejected(db_session):
    from app.game.groups.service import disband_group

    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TRAVEL,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
    )
    disband_group(db_session, group)

    with pytest.raises(OrganizationError):
        found_organization_from_group(
            db_session, group, "Tarde Demais", organization_type=OrganizationType.COMMUNITY,
        )


def test_founding_an_organization_marks_the_group_purpose_completed(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TEMPORARY_ALLIANCE,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
    )

    found_organization_from_group(
        db_session, group, "Os Andarilhos", organization_type=OrganizationType.COMMUNITY,
    )

    assert group.status == GroupStatus.COMPLETED_PURPOSE


def test_falls_back_to_a_member_as_founder_when_the_group_has_no_leader(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TEMPORARY_ALLIANCE,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
    )

    org = found_organization_from_group(
        db_session, group, "Sem Líder Formal", organization_type=OrganizationType.COMMUNITY,
    )

    assert org.founder_id in {character.id, osgar.id}


def test_formal_recognition_is_a_separate_later_step(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    group = create_group(
        db_session, campaign.id, group_type=GroupType.TEMPORARY_ALLIANCE,
        founding_members=[
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, osgar.id),
        ],
    )
    org = found_organization_from_group(
        db_session, group, "Os Andarilhos", organization_type=OrganizationType.COMMUNITY,
    )
    assert org.formality == OrganizationFormality.INFORMAL

    formally_recognize_organization(db_session, org)

    assert org.formality == OrganizationFormality.FORMALLY_RECOGNIZED
