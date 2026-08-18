from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import WorldDevelopmentStatus
from app.core.ids import generate_id
from app.db.base import Base


class WorldDevelopment(Base):
    """
    Persistent state for an ongoing or planned world development.

    WorldEvent records what happened.
    WorldDevelopment represents something that currently exists,
    progresses over in-world time, and may produce events later.
    """

    __tablename__ = "world_developments"

    __table_args__ = (
        Index(
            "ix_world_developments_campaign_status_next_update",
            "campaign_id",
            "status",
            "next_update_world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("dev"),
    )

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )

    region_id: Mapped[str | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
    )

    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
    )

    development_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String,
        default=WorldDevelopmentStatus.PLANNED.value,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String,
        default="",
        nullable=False,
    )

    started_world_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    last_updated_world_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    next_update_world_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    payload_json: Mapped[str] = mapped_column(
        String,
        default="{}",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(
            tzinfo=None
        ),
    )