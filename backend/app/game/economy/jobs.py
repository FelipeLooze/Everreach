"""Phase 14D — Jobs & Work Opportunities.

A Job represents recurring/structured work — farm labor, cook,
carpenter, guard — distinct from a Quest (Phase 12's situation/
objective). The Narrator never employs the player: a job opportunity
existing, a character expressing interest (apply_to_job), and an
employer's decision (resolve_application) are three separate steps —
mirroring exactly how Phase 13B's GroupInvite preserves agency (an
invite is never assumed accepted).

Requirements ("physical capability, some smithing knowledge, employer
willingness"...) are deliberately NOT mechanically checked here — the
spec explicitly warns against an arbitrary "Requires Level 5" gate.
Whoever calls resolve_application is where that judgment happens (a
human, or a future NPC-decision system) — same deferral this project has
used since Phase 13B for "who decides for the NPC."
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    EconomicActorType,
    EventType,
    JobApplicationStatus,
    JobPaymentFrequency,
    JobStatus,
)
from app.db.models.job import Job, JobApplication
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


class JobError(Exception):
    pass


def create_job(
    db: Session,
    campaign_id: str,
    employer_type: EconomicActorType,
    employer_id: str,
    title: str,
    description: str = "",
    *,
    wage_bronze: int,
    payment_frequency: JobPaymentFrequency,
    location_id: str | None = None,
    capacity: int = 1,
) -> Job:
    if not title.strip():
        raise JobError("Um trabalho precisa de um título.")
    if not isinstance(wage_bronze, int) or isinstance(wage_bronze, bool) or wage_bronze < 0:
        raise JobError("O salário precisa ser um inteiro não negativo de Bronze.")
    if capacity < 1:
        raise JobError("Um trabalho precisa de capacidade para ao menos um trabalhador.")

    world_minute = get_world_time(db, campaign_id).total_minutes()
    job = Job(
        campaign_id=campaign_id,
        employer_type=employer_type,
        employer_id=employer_id,
        title=title,
        description=description,
        location_id=location_id,
        wage_bronze=wage_bronze,
        payment_frequency=payment_frequency,
        status=JobStatus.OPEN,
        capacity=capacity,
        created_world_minute=world_minute,
    )
    db.add(job)
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.JOB_CREATED,
        actor_type=employer_type.lower(),
        actor_id=employer_id,
        payload={"job_id": job.id, "title": title, "wage_bronze": wage_bronze},
        occurred_world_minute=world_minute,
    )
    return job


def apply_to_job(
    db: Session, job: Job, applicant_type: CombatActorType, applicant_id: str
) -> JobApplication:
    if job.status != JobStatus.OPEN:
        raise JobError(f"'{job.title}' não está mais aceitando candidaturas ({job.status}).")
    existing = (
        db.query(JobApplication)
        .filter(
            JobApplication.job_id == job.id,
            JobApplication.applicant_type == applicant_type,
            JobApplication.applicant_id == applicant_id,
            JobApplication.status.in_((JobApplicationStatus.PENDING, JobApplicationStatus.ACTIVE)),
        )
        .first()
    )
    if existing is not None:
        return existing

    world_minute = get_world_time(db, job.campaign_id).total_minutes()
    application = JobApplication(
        job_id=job.id,
        applicant_type=applicant_type,
        applicant_id=applicant_id,
        status=JobApplicationStatus.PENDING,
        applied_world_minute=world_minute,
    )
    db.add(application)
    db.flush()

    log_event(
        db,
        job.campaign_id,
        EventType.JOB_APPLICATION_SUBMITTED,
        actor_type=applicant_type.lower(),
        actor_id=applicant_id,
        payload={"job_id": job.id, "application_id": application.id},
        occurred_world_minute=world_minute,
    )
    return application


def resolve_application(
    db: Session, application: JobApplication, *, hired: bool, reason: str = ""
) -> JobApplication:
    """The employer's authoritative decision. Never inferred from
    narration — see the module docstring."""
    if application.status != JobApplicationStatus.PENDING:
        raise JobError(f"Esta candidatura já não está mais pendente ({application.status}).")
    job = db.get(Job, application.job_id)
    world_minute = get_world_time(db, job.campaign_id).total_minutes()

    application.status = JobApplicationStatus.ACTIVE if hired else JobApplicationStatus.REJECTED
    application.resolved_world_minute = world_minute
    db.flush()

    if hired and len(active_workers_for_job(db, job.id)) >= job.capacity:
        job.status = JobStatus.FILLED
        db.flush()

    log_event(
        db,
        job.campaign_id,
        EventType.JOB_APPLICATION_RESOLVED,
        actor_type=application.applicant_type.lower(),
        actor_id=application.applicant_id,
        payload={"job_id": job.id, "hired": hired, "reason": reason},
        occurred_world_minute=world_minute,
    )
    return application


def withdraw_application(db: Session, application: JobApplication) -> JobApplication:
    if application.status != JobApplicationStatus.PENDING:
        raise JobError(f"Esta candidatura já não está mais pendente ({application.status}).")
    world_minute = get_world_time(
        db, db.get(Job, application.job_id).campaign_id
    ).total_minutes()
    application.status = JobApplicationStatus.WITHDRAWN
    application.resolved_world_minute = world_minute
    db.flush()
    return application


def end_employment(db: Session, application: JobApplication, *, reason: str = "") -> JobApplication:
    if application.status != JobApplicationStatus.ACTIVE:
        raise JobError(f"Não é possível encerrar um emprego com status {application.status}.")
    job = db.get(Job, application.job_id)
    world_minute = get_world_time(db, job.campaign_id).total_minutes()
    application.status = JobApplicationStatus.ENDED
    application.resolved_world_minute = world_minute
    db.flush()

    if job.status == JobStatus.FILLED and len(active_workers_for_job(db, job.id)) < job.capacity:
        job.status = JobStatus.OPEN
        db.flush()

    log_event(
        db,
        job.campaign_id,
        EventType.JOB_EMPLOYMENT_ENDED,
        actor_type=application.applicant_type.lower(),
        actor_id=application.applicant_id,
        payload={"job_id": job.id, "reason": reason},
        occurred_world_minute=world_minute,
    )
    return application


def active_workers_for_job(db: Session, job_id: str) -> list[JobApplication]:
    return (
        db.query(JobApplication)
        .filter(JobApplication.job_id == job_id, JobApplication.status == JobApplicationStatus.ACTIVE)
        .all()
    )
