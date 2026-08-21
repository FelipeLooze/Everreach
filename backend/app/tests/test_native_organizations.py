"""Phase 13D — Native Organizations.

origin is always explicit (NATIVE here) — never silently defaulted, since
whether an organization predated transported people is a real world
fact. transported_people_stance is per-organization: two native
organizations may hold genuinely different attitudes toward transported
people, proving nothing here is a single hardcoded universal value.
"""

from app.core.enums import OrganizationOrigin, OrganizationType, TransportedPeopleStance
from app.game.character.service import create_character
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Native Organizations")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_native_organization_has_no_founder_by_default(db_session):
    campaign, region, village, character = _setup(db_session)

    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )

    assert org.origin == OrganizationOrigin.NATIVE
    assert org.founder_type is None
    assert org.transported_people_stance is None


def test_two_native_organizations_may_have_different_stances(db_session):
    campaign, region, village, character = _setup(db_session)

    guild = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
        transported_people_stance=TransportedPeopleStance.WELCOMING,
    )
    cult = create_organization(
        db_session, campaign.id, "Culto Silencioso",
        organization_type=OrganizationType.CRIMINAL, origin=OrganizationOrigin.NATIVE,
        transported_people_stance=TransportedPeopleStance.FEARFUL,
    )

    assert guild.transported_people_stance == TransportedPeopleStance.WELCOMING
    assert cult.transported_people_stance == TransportedPeopleStance.FEARFUL
    assert guild.transported_people_stance != cult.transported_people_stance


def test_stance_is_optional_and_defaults_to_unestablished(db_session):
    campaign, region, village, character = _setup(db_session)

    org = create_organization(
        db_session, campaign.id, "Conselho da Vila",
        organization_type=OrganizationType.POLITICAL, origin=OrganizationOrigin.NATIVE,
    )

    assert org.transported_people_stance is None
