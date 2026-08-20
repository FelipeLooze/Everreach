from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class DomainDefinition(Base):
    __tablename__ = "domain_definitions"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    family: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")


class CharacterDomainEvidence(Base):
    __tablename__ = "character_domain_evidence"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "domain_key",
            name="uq_character_domain_evidence",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("devidence"),
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    domain_key: Mapped[str] = mapped_column(
        ForeignKey("domain_definitions.key"),
        nullable=False,
    )
    depth: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)


class DomainEvidenceRecord(Base):
    __tablename__ = "domain_evidence_records"
    __table_args__ = (
        Index(
            "ix_domain_evidence_character_domain_time",
            "character_id",
            "domain_key",
            "world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("derecord"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    domain_key: Mapped[str] = mapped_column(
        ForeignKey("domain_definitions.key"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    evidence_key: Mapped[str] = mapped_column(String, nullable=False)
    context_key: Mapped[str] = mapped_column(String, nullable=False)
    base_amount: Mapped[float] = mapped_column(Float, nullable=False)
    awarded_amount: Mapped[float] = mapped_column(Float, nullable=False)
    repetition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class CharacterDomainSynergy(Base):
    __tablename__ = "character_domain_synergies"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "first_domain_key",
            "second_domain_key",
            name="uq_character_domain_synergy",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("dsynergy"),
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    first_domain_key: Mapped[str] = mapped_column(
        ForeignKey("domain_definitions.key"),
        nullable=False,
    )
    second_domain_key: Mapped[str] = mapped_column(
        ForeignKey("domain_definitions.key"),
        nullable=False,
    )
    depth: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)


class DomainSynergyRecord(Base):
    __tablename__ = "domain_synergy_records"
    __table_args__ = (
        Index(
            "ix_domain_synergy_character_pair_time",
            "character_id",
            "first_domain_key",
            "second_domain_key",
            "world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("dsrecord"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    first_domain_key: Mapped[str] = mapped_column(
        ForeignKey("domain_definitions.key"),
        nullable=False,
    )
    second_domain_key: Mapped[str] = mapped_column(
        ForeignKey("domain_definitions.key"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    evidence_key: Mapped[str] = mapped_column(String, nullable=False)
    context_key: Mapped[str] = mapped_column(String, nullable=False)
    base_amount: Mapped[float] = mapped_column(Float, nullable=False)
    awarded_amount: Mapped[float] = mapped_column(Float, nullable=False)
    repetition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
