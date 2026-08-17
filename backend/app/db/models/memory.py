from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class Memory(Base):
    """Condensed summary of important happenings, always traceable to source events."""

    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "source_event_id",
            name="uq_memory_owner_source_event",
        ),
        Index(
            "ix_memory_relevant_lookup",
            "campaign_id",
            "owner_type",
            "owner_id",
            "subject",
            "importance",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("mem"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    owner_type: Mapped[str] = mapped_column(String, default="WORLD")
    owner_id: Mapped[str] = mapped_column(String, default="")
    subject: Mapped[str] = mapped_column(String, default="world")
    summary_text: Mapped[str] = mapped_column(String, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("world_events.id"), nullable=True
    )
    source_event_ids_json: Mapped[str] = mapped_column(String, default="[]")
    importance: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
