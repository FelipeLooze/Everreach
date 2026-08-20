from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class AttributeDefinition(Base):
    __tablename__ = "attribute_definitions"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")


class AttributeEvidenceRecord(Base):
    """Hidden evidence of real development; never a player-facing progress bar."""

    __tablename__ = "attribute_evidence_records"
    __table_args__ = (
        Index(
            "ix_attribute_evidence_character_key_time",
            "character_id",
            "attribute_key",
            "world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("aerecord"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    attribute_key: Mapped[str] = mapped_column(
        ForeignKey("attribute_definitions.key"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    evidence_key: Mapped[str] = mapped_column(String, nullable=False)
    context_key: Mapped[str] = mapped_column(String, nullable=False)
    base_amount: Mapped[float] = mapped_column(Float, nullable=False)
    awarded_amount: Mapped[float] = mapped_column(Float, nullable=False)
    repetition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
