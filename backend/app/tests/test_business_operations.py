"""Phase 14K — Business Operations.

A Business is now a real EconomicActorType: it can hold its own funds
(till_bronze, separate from its owner), hire workers and pay wages from
that till (reusing Phase 14D/14E's Job/pay_wage unchanged — Business
composes with existing machinery instead of duplicating it), and run out
of money independently of its owner being broke.
"""

import pytest

from app.core.enums import (
    BusinessType,
    CombatActorType,
    EconomicActorType,
    JobPaymentFrequency,
)
from app.game.character.service import create_character
from app.game.economy.businesses import (
    BusinessError,
    deposit_business_funds,
    found_business,
    withdraw_business_funds,
)
from app.game.economy.jobs import apply_to_job, create_job, resolve_application
from app.game.economy.wages import pay_wage
from app.game.economy.wallet import deposit, get_or_create_holding, total_carried_by_owner
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Business Operations")
    region, village = seed_initial_region(db_session, campaign.id)
    owner = create_character(db_session, campaign.id, "Owner", region.id, village.id)
    worker = create_character(db_session, campaign.id, "Worker", region.id, village.id)
    business = found_business(
        db_session, campaign.id, "Padaria de Cardal", BusinessType.SERVICE,
        owner_type=EconomicActorType.CHARACTER, owner_id=owner.id, location_id=village.id,
    )
    db_session.flush()
    return campaign, region, village, owner, worker, business


def test_business_funds_are_separate_from_the_owners_wallet(db_session):
    campaign, region, village, owner, worker, business = _setup(db_session)
    owner_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, owner.id)
    deposit(db_session, owner_holding, 50, reason="Dinheiro pessoal do dono.")

    deposit_business_funds(db_session, business, 200, reason="Vendas do dia.")

    assert business.till_bronze == 200
    assert owner_holding.amount_bronze == 50


def test_business_can_hire_a_worker_and_pay_from_its_own_till(db_session):
    campaign, region, village, owner, worker, business = _setup(db_session)
    deposit_business_funds(db_session, business, 100, reason="Caixa inicial.")
    job = create_job(
        db_session, campaign.id, EconomicActorType.BUSINESS, business.id, "Padeiro",
        wage_bronze=12, payment_frequency=JobPaymentFrequency.DAILY,
    )
    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, worker.id)
    resolve_application(db_session, application, hired=True)

    paid = pay_wage(db_session, job, application)

    assert paid == 12
    assert business.till_bronze == 88
    assert total_carried_by_owner(db_session, CombatActorType.CHARACTER, worker.id) == 12


def test_business_without_enough_till_cannot_pay_wages(db_session):
    campaign, region, village, owner, worker, business = _setup(db_session)
    job = create_job(
        db_session, campaign.id, EconomicActorType.BUSINESS, business.id, "Padeiro",
        wage_bronze=12, payment_frequency=JobPaymentFrequency.DAILY,
    )
    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, worker.id)
    resolve_application(db_session, application, hired=True)

    from app.game.economy.wages import WageError

    with pytest.raises(WageError):
        pay_wage(db_session, job, application)


def test_withdrawing_more_than_the_till_holds_fails(db_session):
    campaign, region, village, owner, worker, business = _setup(db_session)
    deposit_business_funds(db_session, business, 10, reason="Caixa inicial.")

    with pytest.raises(BusinessError):
        withdraw_business_funds(db_session, business, 50, reason="Compra grande demais.")


def test_business_running_out_of_money_does_not_affect_the_owner(db_session):
    campaign, region, village, owner, worker, business = _setup(db_session)
    owner_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.CHARACTER, owner.id)
    deposit(db_session, owner_holding, 500, reason="Dinheiro pessoal do dono.")

    with pytest.raises(BusinessError):
        withdraw_business_funds(db_session, business, 1, reason="Sem caixa.")

    assert owner_holding.amount_bronze == 500
