"""Phase 14E — Wages & Payment.

pay_wage is the one authoritative path from a Job (Phase 14D) to actual
money moving. An employer must be able to afford it — this is not a new
rule invented here, it falls straight out of reusing the real holdings
via withdraw_from_actor (Phase 14J's shared actor-funds helper), which
already refuses an amount the employer doesn't have. There is no
infinite employer money.

Payment frequency (Job.payment_frequency, Phase 14D) is not
automatically scheduled here — pay_wage is an explicit, callable action;
deciding WHEN it fires (daily tick, end of a task, a contract clause) is
future/world-simulation work, not this subphase's job.
"""

from sqlalchemy.orm import Session

from app.core.enums import EventType, JobApplicationStatus
from app.db.models.job import Job, JobApplication
from app.game.economy.actors import ActorFundsError, deposit_to_actor, withdraw_from_actor
from app.services.event_log import log_event


class WageError(Exception):
    pass


def pay_wage(
    db: Session,
    job: Job,
    application: JobApplication,
    *,
    amount_bronze: int | None = None,
    reason: str = "Pagamento de salário",
) -> int:
    if application.job_id != job.id:
        raise WageError("Esta candidatura não pertence a este trabalho.")
    if application.status != JobApplicationStatus.ACTIVE:
        raise WageError(f"Não é possível pagar um vínculo com status {application.status}.")

    amount = amount_bronze if amount_bronze is not None else job.wage_bronze
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise WageError("O salário pago precisa ser um inteiro positivo de Bronze.")

    try:
        withdraw_from_actor(db, job.employer_type, job.employer_id, job.campaign_id, amount, reason=reason)
    except ActorFundsError as exc:
        raise WageError(str(exc)) from exc

    deposit_to_actor(
        db, application.applicant_type, application.applicant_id, job.campaign_id, amount, reason=reason
    )

    log_event(
        db,
        job.campaign_id,
        EventType.WAGE_PAID,
        actor_type=application.applicant_type.lower(),
        actor_id=application.applicant_id,
        payload={"job_id": job.id, "application_id": application.id, "amount_bronze": amount},
    )
    return amount
