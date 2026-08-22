from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("campaign"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

    world_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    world_time: Mapped["WorldTime"] = relationship(
        back_populates="campaign", uselist=False, cascade="all, delete-orphan"
    )


class WorldTime(Base):
    """Single-row-per-campaign in-world clock."""

    __tablename__ = "world_times"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("time"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), unique=True, nullable=False)

    year: Mapped[int] = mapped_column(Integer, default=1)
    month: Mapped[int] = mapped_column(Integer, default=1)
    day: Mapped[int] = mapped_column(Integer, default=1)
    hour: Mapped[int] = mapped_column(Integer, default=8)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    subminute_seconds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )


    campaign: Mapped["Campaign"] = relationship(back_populates="world_time")

    def total_minutes(self) -> int:
        """Minutes since year 1/month 1/day 1 00:00, assuming 30-day months, 12-month years."""
        return (
            (((self.year - 1) * 12 + (self.month - 1)) * 30 + (self.day - 1)) * 24 * 60
            + self.hour * 60
            + self.minute
        )
