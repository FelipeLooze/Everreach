"""Phase 14L — Organization Economy Integration.

Most of what this subphase asks for already composes with zero new code
once Organization became a real EconomicActorType (Phase 14J/14K) — the
first three tests prove that directly (Job/pay_wage/found_business
already accept an Organization unchanged). The genuinely new code is
organization_purchase_item/organization_sell_asset — the purchase/sale
counterpart to Phase 13J's OrganizationAsset overlay, needed because
ItemInstance ownership is DB-constrained to CHARACTER/NPC and an
Organization can never directly own one.
"""

import pytest

from app.core.enums import (
    BusinessType,
    CombatActorType,
    EconomicActorType,
    JobPaymentFrequency,
    OrganizationOrigin,
    OrganizationType,
)
from app.game.character.service import create_character
from app.game.economy.businesses import found_business
from app.game.economy.jobs import apply_to_job, create_job, resolve_application
from app.game.economy.pricing import set_item_base_value
from app.game.economy.wages import pay_wage
from app.game.economy.wallet import get_or_create_holding, total_carried_by_owner
from app.game.inventory.service import add_item, get_or_create_item
from app.game.organizations.assets import deposit_funds, organization_assets
from app.game.organizations.economy import (
    OrganizationEconomyError,
    organization_purchase_item,
    organization_sell_asset,
)
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Organization Economy")
    region, village = seed_initial_region(db_session, campaign.id)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, org, character


# --- integration proof: existing machinery already composes ---------------


def test_organization_can_hire_and_pay_a_worker_unchanged(db_session):
    campaign, region, village, org, character = _setup(db_session)
    deposit_funds(db_session, org, 100, reason="Fundos da guilda.")
    job = create_job(
        db_session, campaign.id, EconomicActorType.ORGANIZATION, org.id, "Caçador contratado",
        wage_bronze=15, payment_frequency=JobPaymentFrequency.DAILY,
    )
    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)
    resolve_application(db_session, application, hired=True)

    paid = pay_wage(db_session, job, application)

    assert paid == 15
    assert org.treasury == 85


def test_organization_can_own_a_business_unchanged(db_session):
    campaign, region, village, org, character = _setup(db_session)
    deposit_funds(db_session, org, 200, reason="Fundos da guilda.")

    business = found_business(
        db_session, campaign.id, "Armazém da Guilda", BusinessType.TRADING_COMPANY,
        owner_type=EconomicActorType.ORGANIZATION, owner_id=org.id, startup_cost_bronze=150,
    )

    assert business.owner_id == org.id
    assert org.treasury == 50


# --- organization_purchase_item / organization_sell_asset -----------------


def test_organization_purchases_an_item_through_an_agent(db_session):
    from app.db.models.npc import NPC

    campaign, region, village, org, character = _setup(db_session)
    agent = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    deposit_funds(db_session, org, 100, reason="Fundos da guilda.")
    definition = get_or_create_item(db_session, "Arco Longo")
    set_item_base_value(db_session, definition, 40)
    bow = add_item(db_session, character.id, "Arco Longo")

    price = organization_purchase_item(
        db_session, org, bow,
        agent_type=CombatActorType.NPC, agent_id=agent.id,
        seller_type=EconomicActorType.CHARACTER, seller_id=character.id,
    )

    assert price == 40
    assert org.treasury == 60
    assert bow.owner_ref == agent.id
    seller_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, character.id)
    assert seller_holding.amount_bronze == 40


def test_organization_purchase_fails_without_enough_treasury(db_session):
    campaign, region, village, org, character = _setup(db_session)
    definition = get_or_create_item(db_session, "Espada Cara")
    set_item_base_value(db_session, definition, 500)
    sword = add_item(db_session, character.id, "Espada Cara")

    with pytest.raises(OrganizationEconomyError):
        organization_purchase_item(
            db_session, org, sword,
            agent_type=CombatActorType.CHARACTER, agent_id=character.id,
            seller_type=EconomicActorType.CHARACTER, seller_id=character.id,
        )


def test_purchased_item_becomes_organization_asset(db_session):
    campaign, region, village, org, character = _setup(db_session)
    seller = create_character(db_session, campaign.id, "Seller", region.id, village.id)
    deposit_funds(db_session, org, 100, reason="Fundos da guilda.")
    definition = get_or_create_item(db_session, "Machado")
    set_item_base_value(db_session, definition, 20)
    axe = add_item(db_session, seller.id, "Machado")

    organization_purchase_item(
        db_session, org, axe,
        agent_type=CombatActorType.CHARACTER, agent_id=character.id,
        seller_type=EconomicActorType.CHARACTER, seller_id=seller.id,
    )

    assert axe in organization_assets(db_session, org.id)
    assert axe.owner_ref == character.id


def test_organization_sells_one_of_its_own_assets(db_session):
    campaign, region, village, org, character = _setup(db_session)
    seller = create_character(db_session, campaign.id, "Seller", region.id, village.id)
    definition = get_or_create_item(db_session, "Picareta")
    set_item_base_value(db_session, definition, 15)
    pick = add_item(db_session, seller.id, "Picareta")
    deposit_funds(db_session, org, 100, reason="Fundos da guilda.")
    organization_purchase_item(
        db_session, org, pick,
        agent_type=CombatActorType.CHARACTER, agent_id=character.id,
        seller_type=EconomicActorType.CHARACTER, seller_id=seller.id,
    )
    owned_item = organization_assets(db_session, org.id)[0]
    buyer = create_character(db_session, campaign.id, "Buyer", region.id, village.id)
    buyer_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, buyer.id)
    from app.game.economy.wallet import deposit
    deposit(db_session, buyer_holding, 50, reason="Saldo inicial.")
    treasury_before = org.treasury

    price = organization_sell_asset(
        db_session, org, owned_item, buyer_type=CombatActorType.CHARACTER, buyer_id=buyer.id,
    )

    assert price == 15
    assert org.treasury == treasury_before + 15
    assert pick.owner_ref == buyer.id
    assert organization_assets(db_session, org.id) == []
