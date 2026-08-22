"""Phase 14E — Wages & Payment.

pay_wage always moves real money from a real holding — an employer
(character/NPC or an Organization) that cannot afford it fails loudly,
not silently. No infinite employer money: this falls straight out of
reusing the real Phase 13J/14A holdings, nothing new invented here.
"""

import pytest

from app.core.enums import (
    CombatActorType,
    EconomicActorType,
    JobPaymentFrequency,
    OrganizationOrigin,
    OrganizationType,
)
from app.game.character.service import create_character
from app.game.economy.jobs import apply_to_job, create_job, resolve_application
from app.game.economy.wages import WageError, pay_wage
from app.game.economy.wallet import deposit, get_or_create_holding, total_carried_by_owner
from app.game.organizations.assets import deposit_funds
from app.game.organizations.service import create_organization
from app.game.world.seed import create_campaign, seed_initial_region
from app.db.models.npc import NPC


def _setup(db_session):
    campaign = create_campaign(db_session, "Wages")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()
    db_session.flush()
    return campaign, region, village, character, osgar


def _hired_application(db_session, campaign, employer_type, employer_id, worker_id, wage=10):
    job = create_job(
        db_session, campaign.id, employer_type, employer_id, "Trabalho de teste",
        wage_bronze=wage, payment_frequency=JobPaymentFrequency.PER_TASK,
    )
    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, worker_id)
    resolve_application(db_session, application, hired=True)
    return job, application


def test_paying_moves_money_from_npc_employer_to_worker(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    employer_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.NPC, osgar.id)
    deposit(db_session, employer_holding, 50, reason="Fundos do NPC.")
    job, application = _hired_application(
        db_session, campaign, EconomicActorType.NPC, osgar.id, character.id, wage=6
    )

    paid = pay_wage(db_session, job, application)

    assert paid == 6
    assert employer_holding.amount_bronze == 44
    assert total_carried_by_owner(db_session, CombatActorType.CHARACTER, character.id) == 6


def test_npc_employer_without_enough_funds_fails(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    job, application = _hired_application(
        db_session, campaign, EconomicActorType.NPC, osgar.id, character.id, wage=6
    )

    with pytest.raises(WageError):
        pay_wage(db_session, job, application)


def test_organization_employer_pays_from_treasury(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    org = create_organization(
        db_session, campaign.id, "Guilda dos Caçadores de Cardal",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    deposit_funds(db_session, org, 100, reason="Fundos iniciais.")
    job, application = _hired_application(
        db_session, campaign, EconomicActorType.ORGANIZATION, org.id, character.id, wage=15
    )

    paid = pay_wage(db_session, job, application)

    assert paid == 15
    assert org.treasury == 85
    assert total_carried_by_owner(db_session, CombatActorType.CHARACTER, character.id) == 15


def test_organization_employer_without_enough_treasury_fails(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    org = create_organization(
        db_session, campaign.id, "Guilda Pobre",
        organization_type=OrganizationType.GUILD, origin=OrganizationOrigin.NATIVE,
    )
    job, application = _hired_application(
        db_session, campaign, EconomicActorType.ORGANIZATION, org.id, character.id, wage=15
    )

    with pytest.raises(WageError):
        pay_wage(db_session, job, application)

    assert org.treasury == 0


def test_cannot_pay_a_non_active_application(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Trabalho",
        wage_bronze=6, payment_frequency=JobPaymentFrequency.PER_TASK,
    )
    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)

    with pytest.raises(WageError):
        pay_wage(db_session, job, application)


def test_explicit_amount_overrides_the_job_wage(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    employer_holding = get_or_create_holding(db_session, campaign.id, CombatActorType.NPC, osgar.id)
    deposit(db_session, employer_holding, 50, reason="Fundos do NPC.")
    job, application = _hired_application(
        db_session, campaign, EconomicActorType.NPC, osgar.id, character.id, wage=6
    )

    paid = pay_wage(db_session, job, application, amount_bronze=20, reason="Bônus.")

    assert paid == 20
