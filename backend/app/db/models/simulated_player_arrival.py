from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class ScheduledSimulatedPlayerArrival(Base):
    """
    A future arrival of transported people.

    Scheduling does not create identities and does not change abstract
    population. Execution happens later when world time reaches the
    scheduled minute.
    """

    __tablename__ = "scheduled_simulated_player_arrivals"

    __table_args__ = (
        Index(
            "ix_scheduled_simulated_player_arrival_due",
            "scheduled_world_minute",
            "executed_world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("sparr"),
    )

    location_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id"),
        nullable=False,
    )

    scheduled_world_minute: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    executed_world_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )