from sqlalchemy import (
    Boolean,
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

class SimulatedPlayerArrivalPolicy(Base):
    """
    Per-campaign policy for future transported-person arrivals.

    Absence of a row means automatic later arrivals are not configured
    for the campaign.

    The policy stores timing and group-size bounds only. It does not
    decide where an arrival occurs.
    """

    __tablename__ = "simulated_player_arrival_policies"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("sppolicy"),
    )

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        unique=True,
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    min_delay_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    max_delay_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    min_group_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    max_group_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )