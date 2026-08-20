from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class CharacterResourceGrowth(Base):
    __tablename__ = "character_resource_growth"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "resource_key",
            name="uq_character_resource_growth",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("resourcegrowth"),
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    resource_key: Mapped[str] = mapped_column(String, nullable=False)
    development: Mapped[float] = mapped_column(Float, default=0.0)


class ResourceGrowthEvidenceRecord(Base):
    __tablename__ = "resource_growth_evidence_records"
    __table_args__ = (
        Index(
            "ix_resource_growth_evidence_character_key_time",
            "character_id",
            "resource_key",
            "world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("rgerecord"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    resource_key: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    contributing_attribute_key: Mapped[str | None] = mapped_column(
        ForeignKey("attribute_definitions.key"),
        nullable=True,
    )
    evidence_key: Mapped[str] = mapped_column(String, nullable=False)
    context_key: Mapped[str] = mapped_column(String, nullable=False)
    base_amount: Mapped[float] = mapped_column(Float, nullable=False)
    awarded_amount: Mapped[float] = mapped_column(Float, nullable=False)
    repetition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
