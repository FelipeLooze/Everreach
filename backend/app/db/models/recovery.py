from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.db.base import Base


class CharacterRecovery(Base):
    """One authoritative and idempotent recovery period for the protagonist."""

    __tablename__ = "character_recoveries"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "recovery_key",
            name="uq_character_recovery_key",
        ),
        Index(
            "ix_character_recovery_campaign_time",
            "campaign_id",
            "started_world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("recovery"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    recovery_key: Mapped[str] = mapped_column(String, nullable=False)
    recovery_type: Mapped[str] = mapped_column(String, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    started_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    hp_before: Mapped[float] = mapped_column(Float, nullable=False)
    hp_after: Mapped[float] = mapped_column(Float, nullable=False)
    mana_before: Mapped[float] = mapped_column(Float, nullable=False)
    mana_after: Mapped[float] = mapped_column(Float, nullable=False)
    stamina_before: Mapped[float] = mapped_column(Float, nullable=False)
    stamina_after: Mapped[float] = mapped_column(Float, nullable=False)

    character: Mapped["Character"] = relationship()
