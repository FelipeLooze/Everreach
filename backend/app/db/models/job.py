from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import JobApplicationStatus, JobStatus
from app.core.ids import generate_id
from app.db.base import Base


class Job(Base):
    """Phase 14D — recurring or structured work, distinct from a Quest
    (Phase 12, a situation/objective). employer_type is EconomicActorType
    (Organizations may employ, Phase 14L) — workers are CombatActorType
    on JobApplication below, since only living actors work."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("job"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    employer_type: Mapped[str] = mapped_column(String, nullable=False)
    employer_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="", nullable=False)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    wage_bronze: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_frequency: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default=JobStatus.OPEN, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class JobApplication(Base):
    """One row per employment stint (mirrors OrganizationMember, Phase
    13F) — a rejection followed by a later successful application, or an
    employment that ended and was later resumed, stay distinct preserved
    facts rather than one row silently overwritten."""

    __tablename__ = "job_applications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("japp"))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    applicant_type: Mapped[str] = mapped_column(String, nullable=False)
    applicant_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default=JobApplicationStatus.PENDING, nullable=False)
    applied_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
