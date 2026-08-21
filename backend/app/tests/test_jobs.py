"""Phase 14D — Jobs & Work Opportunities.

The Narrator never employs the player: opportunity, application, and the
employer's own decision are three separate authoritative steps. A Job is
distinct from a Quest — no objectives, just recurring work with a wage
and a capacity of workers.
"""

import pytest

from app.core.enums import CombatActorType, EconomicActorType, JobPaymentFrequency, JobStatus
from app.game.character.service import create_character
from app.game.economy.jobs import (
    JobError,
    active_workers_for_job,
    apply_to_job,
    create_job,
    end_employment,
    resolve_application,
    withdraw_application,
)
from app.game.world.seed import create_campaign, seed_initial_region
from app.db.models.npc import NPC


def _setup(db_session):
    campaign = create_campaign(db_session, "Jobs")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    osgar = db_session.query(NPC).filter(NPC.name == "Osgar Vell").first()
    db_session.flush()
    return campaign, region, village, character, osgar


def test_applying_does_not_hire_automatically(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Descarregar carroças",
        wage_bronze=6, payment_frequency=JobPaymentFrequency.PER_TASK,
    )

    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)

    assert application.status == "PENDING"
    assert active_workers_for_job(db_session, job.id) == []


def test_employer_can_reject_an_application(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Guarda noturno",
        wage_bronze=15, payment_frequency=JobPaymentFrequency.DAILY,
    )
    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)

    resolve_application(db_session, application, hired=False, reason="Sem experiência suficiente.")

    assert application.status == "REJECTED"
    assert active_workers_for_job(db_session, job.id) == []


def test_hiring_creates_active_employment(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Ajudante de ferreiro",
        wage_bronze=12, payment_frequency=JobPaymentFrequency.DAILY,
    )
    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)

    resolve_application(db_session, application, hired=True)

    assert application.status == "ACTIVE"
    assert [a.id for a in active_workers_for_job(db_session, job.id)] == [application.id]


def test_job_fills_up_once_capacity_is_reached(db_session):
    from app.game.character.service import create_character as _create

    campaign, region, village, character, osgar = _setup(db_session)
    second = _create(db_session, campaign.id, "Second", region.id, village.id)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Colheita",
        wage_bronze=8, payment_frequency=JobPaymentFrequency.DAILY, capacity=2,
    )
    first_app = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)
    second_app = apply_to_job(db_session, job, CombatActorType.CHARACTER, second.id)
    resolve_application(db_session, first_app, hired=True)
    assert job.status == JobStatus.OPEN

    resolve_application(db_session, second_app, hired=True)

    assert job.status == JobStatus.FILLED


def test_cannot_apply_to_a_filled_job(db_session):
    from app.game.character.service import create_character as _create

    campaign, region, village, character, osgar = _setup(db_session)
    other = _create(db_session, campaign.id, "Other", region.id, village.id)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Trabalho único",
        wage_bronze=8, payment_frequency=JobPaymentFrequency.PER_TASK, capacity=1,
    )
    app = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)
    resolve_application(db_session, app, hired=True)

    with pytest.raises(JobError):
        apply_to_job(db_session, job, CombatActorType.CHARACTER, other.id)


def test_ending_employment_reopens_a_filled_job(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Trabalho único",
        wage_bronze=8, payment_frequency=JobPaymentFrequency.PER_TASK, capacity=1,
    )
    app = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)
    resolve_application(db_session, app, hired=True)
    assert job.status == JobStatus.FILLED

    end_employment(db_session, app, reason="Fim do contrato.")

    assert job.status == JobStatus.OPEN
    assert active_workers_for_job(db_session, job.id) == []


def test_withdrawing_a_pending_application(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Trabalho qualquer",
        wage_bronze=8, payment_frequency=JobPaymentFrequency.PER_TASK,
    )
    application = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)

    withdraw_application(db_session, application)

    assert application.status == "WITHDRAWN"


def test_reapplying_after_withdrawal_creates_a_new_application(db_session):
    campaign, region, village, character, osgar = _setup(db_session)
    job = create_job(
        db_session, campaign.id, EconomicActorType.NPC, osgar.id, "Trabalho qualquer",
        wage_bronze=8, payment_frequency=JobPaymentFrequency.PER_TASK,
    )
    first = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)
    withdraw_application(db_session, first)

    second = apply_to_job(db_session, job, CombatActorType.CHARACTER, character.id)

    assert second.id != first.id
