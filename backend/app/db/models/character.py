from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import CharacterStatus
from app.core.ids import generate_id
from app.db.base import Base


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("char"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    profession_affinity_key: Mapped[str | None] = mapped_column(
        ForeignKey("professions.key"),
        nullable=True,
    )
    active_class_id: Mapped[str | None] = mapped_column(
        ForeignKey("class_definitions.id"),
        nullable=True,
    )

    level: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[float] = mapped_column(Float, default=0)

    hp_current: Mapped[float] = mapped_column(Float, default=20)
    hp_max: Mapped[float] = mapped_column(Float, default=20)
    mana_current: Mapped[float] = mapped_column(Float, default=10)
    mana_max: Mapped[float] = mapped_column(Float, default=10)
    stamina_current: Mapped[float] = mapped_column(Float, default=20)
    stamina_max: Mapped[float] = mapped_column(Float, default=20)

    status: Mapped[str] = mapped_column(String, default=CharacterStatus.ALIVE)

    region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

    attributes: Mapped[list["CharacterAttribute"]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )
    professions: Mapped[list["CharacterProfession"]] = relationship(
        cascade="all, delete-orphan"
    )
    class_offers: Mapped[list["CharacterClassOffer"]] = relationship(
        cascade="all, delete-orphan"
    )


class CharacterAttribute(Base):
    """Extensible primary attributes (Strength, Agility, ...). Not hardcoded as columns
    so new attributes can be introduced later without a schema migration per-attribute."""

    __tablename__ = "character_attributes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("attr"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[int] = mapped_column(Integer, default=10)

    character: Mapped["Character"] = relationship(back_populates="attributes")
