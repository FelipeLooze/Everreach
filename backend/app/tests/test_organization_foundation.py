"""Phase 13C — Organization Foundation.

Foundation only — the entity itself, persisting independent of the
protagonist, with no members/roles/reputation/goals yet. One general
model covers every organization type (no separate GuildTable etc.).
"""

import pytest

from app.core.enums import (
    CombatActorType,
    OrganizationOrigin,
    OrganizationStatus,
    OrganizationType,
    OrganizationVisibility,
)
from app.game.character.service import create_character
from app.game.organizations.service import (
    OrganizationError,
    create_organization,
    set_organization_status,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Foundation")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_organization_can_be_created_with_minimal_identity(db_session):
    campaign, region, village, character = _setup(db_session)

    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )

    assert org.status == OrganizationStatus.ACTIVE
    assert org.visibility == OrganizationVisibility.PUBLIC
    assert org.headquarters_location_id is None
    assert org.founder_type is None


def test_organization_does_not_require_headquarters_or_founder(db_session):
    campaign, region, village, character = _setup(db_session)

    org = create_organization(
        db_session, campaign.id, "Culto Silencioso",
        organization_type=OrganizationType.CRIMINAL, origin=OrganizationOrigin.NATIVE,
        visibility=OrganizationVisibility.SECRET,
    )

    assert org.headquarters_location_id is None
    assert org.visibility == OrganizationVisibility.SECRET


def test_organization_may_have_a_transported_founder(db_session):
    campaign, region, village, character = _setup(db_session)

    org = create_organization(
        db_session, campaign.id, "Os Andarilhos",
        organization_type=OrganizationType.COMMUNITY, origin=OrganizationOrigin.TRANSPORTED_CREATED,
        founder_type=CombatActorType.CHARACTER, founder_id=character.id,
    )

    assert org.founder_type == CombatActorType.CHARACTER
    assert org.founder_id == character.id


def test_organization_requires_a_name(db_session):
    campaign, region, village, character = _setup(db_session)

    with pytest.raises(OrganizationError):
        create_organization(
            db_session, campaign.id, "  ",
            organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
        )


def test_status_change_preserves_the_organization_row(db_session):
    campaign, region, village, character = _setup(db_session)
    org = create_organization(
        db_session, campaign.id, "Companhia Mercante de Cardal",
        organization_type=OrganizationType.COMMERCIAL, origin=OrganizationOrigin.NATIVE,
    )

    set_organization_status(db_session, org, OrganizationStatus.DISBANDED)

    assert org.status == OrganizationStatus.DISBANDED
    assert org.id is not None


def test_status_change_to_the_same_status_is_a_noop(db_session):
    campaign, region, village, character = _setup(db_session)
    org = create_organization(
        db_session, campaign.id, "Ordem Militar",
        organization_type=OrganizationType.MILITARY, origin=OrganizationOrigin.NATIVE,
    )

    result = set_organization_status(db_session, org, OrganizationStatus.ACTIVE)

    assert result.status == OrganizationStatus.ACTIVE
