from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class WorldEvent(Base):
    """Append-only structured event log. This is the source of truth for what happened —
    never rely on LLM conversation history as memory."""

    __tablename__ = "world_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("evt"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)

    actor_type: Mapped[str] = mapped_column(String, default="")
    actor_id: Mapped[str] = mapped_column(String, default="")

    payload_json: Mapped[str] = mapped_column(String, default="{}")

    world_minute: Mapped[int] = mapped_column(Integer, default=0)
    importance: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
