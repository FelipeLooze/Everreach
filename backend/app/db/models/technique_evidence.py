from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class CharacterTechniquePatternEvidence(Base):
    """Accumulated reproducibility of one specific attempted maneuver — a
    'pattern_key' identifies the maneuver itself, not yet a recognized
    Technique (none may exist for it). Mirrors CharacterDomainEvidence's
    shape; domain_keys/technique_type are pinned on first evidence and must
    stay consistent afterward, same rule create_technique already applies to
    a real Technique's domains."""

    __tablename__ = "character_technique_pattern_evidence"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "pattern_key",
            name="uq_character_technique_pattern_evidence",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("tpevidence")
    )
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    pattern_key: Mapped[str] = mapped_column(String, nullable=False)
    domain_keys: Mapped[str] = mapped_column(String, nullable=False)
    technique_type: Mapped[str] = mapped_column(String, nullable=False)
    depth: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)


class TechniquePatternEvidenceRecord(Base):
    """Append-only log of one award, mirroring DomainEvidenceRecord."""

    __tablename__ = "technique_pattern_evidence_records"
    __table_args__ = (
        Index(
            "ix_technique_pattern_evidence_character_pattern_time",
            "character_id",
            "pattern_key",
            "world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("tperecord")
    )
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    pattern_key: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    evidence_key: Mapped[str] = mapped_column(String, nullable=False)
    context_key: Mapped[str] = mapped_column(String, nullable=False)
    base_amount: Mapped[float] = mapped_column(Float, nullable=False)
    awarded_amount: Mapped[float] = mapped_column(Float, nullable=False)
    repetition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class TechniqueExperimentRecord(Base):
    """Idempotent mechanical result of one freeform technique-pattern
    attempt (Phase 11I) — mirrors TechniqueUseRecord's shape (a real,
    already-learned technique's use), but for a not-yet-recognized
    maneuver. action_key uniqueness prevents a retry from rolling twice or
    double-spending the resource cost."""

    __tablename__ = "technique_experiment_records"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "character_id",
            "action_key",
            name="uq_technique_experiment_action",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("texperiment")
    )
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    pattern_key: Mapped[str] = mapped_column(String, nullable=False)
    domain_keys: Mapped[str] = mapped_column(String, nullable=False)
    technique_type: Mapped[str] = mapped_column(String, nullable=False)
    action_key: Mapped[str] = mapped_column(String, nullable=False)
    roll: Mapped[int] = mapped_column(Integer, nullable=False)
    modifier: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    dc: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    resource_key: Mapped[str] = mapped_column(String, nullable=False)
    resource_cost: Mapped[float] = mapped_column(Float, nullable=False)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
