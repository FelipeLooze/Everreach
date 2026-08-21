from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class OrganizationReputationRecord(Base):
    """Phase 13G — append-only reputation history, mirroring
    DomainEvidenceRecord/TechniquePatternEvidenceRecord's shape. This is
    the "reputation reasons/history" the spec requires — a raw numeric
    score (see app.game.organizations.reputation) is derived from these
    records, never the other way around, and is never the only source of
    truth on its own."""

    __tablename__ = "organization_reputation_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("orep"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
