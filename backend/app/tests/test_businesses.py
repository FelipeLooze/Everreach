"""Phase 14J — Businesses & Ownership.

No "[CREATE BUSINESS]" button — founding with a startup cost requires the
owner to actually afford and spend it. Owner != operator: an Organization
may own a business a character or NPC actually runs day to day.
"""

import pytest

from app.core.enums import (
    BusinessStatus,
    BusinessType,
    CombatActorType,
    EconomicActorType,
    OrganizationOrigin,
    OrganizationType,
)
from app.game.character.service import create_character
from app.game.economy.businesses import (
    BusinessError,
    businesses_owned_by,
    change_operator,
    close_business,
    found_business,
)
from app.game.economy.wallet import deposit, get_or_create_holding
from app.game.organizations.assets import deposit_funds
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Businesses")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Cook", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_founding_with_no_startup_cost_requires_no_capital(db_session):
    campaign, region, village, character = _setup(db_session)

    business = found_business(
        db_session, campaign.id, "Barraca de Sopa", BusinessType.RESTAURANT,
        owner_type=EconomicActorType.CHARACTER, owner_id=character.id,
        location_id=village.id,
    )

    assert business.status == BusinessStatus.ACTIVE
    assert business.operator_type is None


def test_founding_with_a_startup_cost_spends_real_capital(db_session):
    campaign, region, village, character = _setup(db_session)
    holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    deposit(db_session, holding, 100, reason="Economias.")

    found_business(
        db_session, campaign.id, "Estalagem", BusinessType.INN,
        owner_type=EconomicActorType.CHARACTER, owner_id=character.id,
        location_id=village.id, startup_cost_bronze=60,
    )

    assert holding.amount_bronze == 40


def test_founding_without_enough_capital_fails(db_session):
    campaign, region, village, character = _setup(db_session)

    with pytest.raises(BusinessError):
        found_business(
            db_session, campaign.id, "Estalagem Cara", BusinessType.INN,
            owner_type=EconomicActorType.CHARACTER, owner_id=character.id,
            location_id=village.id, startup_cost_bronze=100,
        )


def test_organization_can_own_a_business(db_session):
    campaign, region, village, character = _setup(db_session)
    org = create_organization(
        db_session, campaign.id, "Companhia Mercante de Cardal",
        organization_type=OrganizationType.COMMERCIAL, origin=OrganizationOrigin.NATIVE,
    )
    deposit_funds(db_session, org, 200, reason="Capital da companhia.")

    business = found_business(
        db_session, campaign.id, "Armazém da Companhia", BusinessType.TRADING_COMPANY,
        owner_type=EconomicActorType.ORGANIZATION, owner_id=org.id,
        operator_type=CombatActorType.CHARACTER, operator_id=character.id,
        startup_cost_bronze=150,
    )

    assert business.owner_type == "ORGANIZATION"
    assert business.owner_id == org.id
    assert business.operator_id == character.id
    assert org.treasury == 50
    assert businesses_owned_by(db_session, EconomicActorType.ORGANIZATION, org.id) == [business]


def test_owner_may_change_the_operator(db_session):
    campaign, region, village, character = _setup(db_session)
    other = create_character(db_session, campaign.id, "Waiter", region.id, village.id)
    business = found_business(
        db_session, campaign.id, "Taverna", BusinessType.TAVERN,
        owner_type=EconomicActorType.CHARACTER, owner_id=character.id,
        operator_type=CombatActorType.CHARACTER, operator_id=character.id,
    )

    change_operator(db_session, business, CombatActorType.CHARACTER, other.id)

    assert business.operator_id == other.id
    assert business.owner_id == character.id  # ownership itself never changed


def test_closing_a_business(db_session):
    campaign, region, village, character = _setup(db_session)
    business = found_business(
        db_session, campaign.id, "Loja Fechada", BusinessType.SHOP,
        owner_type=EconomicActorType.CHARACTER, owner_id=character.id,
    )

    close_business(db_session, business, reason="Sem clientes.")

    assert business.status == BusinessStatus.CLOSED


def test_operator_type_and_id_must_be_given_together(db_session):
    campaign, region, village, character = _setup(db_session)

    with pytest.raises(BusinessError):
        found_business(
            db_session, campaign.id, "Negócio Inválido", BusinessType.OTHER,
            owner_type=EconomicActorType.CHARACTER, owner_id=character.id,
            operator_type=CombatActorType.CHARACTER, operator_id=None,
        )
