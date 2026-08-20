from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class AppliedProgressionOutcome(Base):
    """Idempotency boundary between mechanical resolvers and progression."""

    __tablename__ = "applied_progression_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "character_id",
            "outcome_key",
            name="uq_applied_progression_outcome",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("progressionoutcome"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"),
        nullable=False,
    )
    outcome_key: Mapped[str] = mapped_column(String, nullable=False)
    applied_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
