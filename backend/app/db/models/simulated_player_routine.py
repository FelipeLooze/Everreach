from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class SimulatedPlayerRoutine(Base):
    """
    A recurring daily local routine for one persistent transported person.

    The routine describes an established habit. It does not itself change
    the person's current activity; player simulation resolves that later.
    """

    __tablename__ = "simulated_player_routines"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("sproutine"),
    )

    simulated_player_id: Mapped[str] = mapped_column(
        ForeignKey("simulated_players.id"),
        nullable=False,
    )

    location_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id"),
        nullable=False,
    )

    activity: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    start_minute_of_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    end_minute_of_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    established_world_minute: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )