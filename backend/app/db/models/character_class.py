from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
        Index(
            "uq_class_definition_campaign_generation_key",
            "campaign_id",
            "generation_key",
            unique=True,
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
    identity: Mapped[str] = mapped_column(Text, default="")
    theme: Mapped[str] = mapped_column(String, default="")
    generation_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    domains: Mapped[list["ClassDefinitionDomain"]] = relationship(
        cascade="all, delete-orphan",
        order_by="ClassDefinitionDomain.domain_key",
    )


class ClassDefinitionDomain(Base):
    """A factual domain recognized by a generated class identity."""

    __tablename__ = "class_definition_domains"

    class_definition_id: Mapped[str] = mapped_column(
        ForeignKey("class_definitions.id"),
        primary_key=True,
    )
    domain_key: Mapped[str] = mapped_column(
        ForeignKey("domain_definitions.key"),
        primary_key=True,
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
    sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    class_definition: Mapped["ClassDefinition"] = relationship()
