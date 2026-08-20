from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ClassOfferStatus
from app.core.ids import generate_id
from app.db.base import Base


class ClassDefinition(Base):
    """A class identity recognized inside one campaign; it grants no powers by itself."""

    __tablename__ = "class_definitions"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "name",
            name="uq_class_definition_campaign_name",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("class"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )


class CharacterClassOffer(Base):
    __tablename__ = "character_class_offers"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "class_definition_id",
            name="uq_character_class_offer",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("coffer"),
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    class_definition_id: Mapped[str] = mapped_column(
        ForeignKey("class_definitions.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String,
        default=ClassOfferStatus.PENDING.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    class_definition: Mapped["ClassDefinition"] = relationship()
