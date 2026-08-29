from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class ActionCheckpoint(Base):
    """Persistent pre-action snapshot used for one safe, bounded undo.

    Campaign and character ids deliberately are not foreign keys: restoration
    temporarily deletes and recreates domain rows inside one deferred
    transaction while this control record must remain available.
    """

    __tablename__ = "action_checkpoints"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("checkpoint")
    )
    campaign_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    character_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action_key: Mapped[str] = mapped_column(String, nullable=False)
    player_text: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    post_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    narrative: Mapped[str] = mapped_column(Text, default="", nullable=False)
    mechanical_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String, default="CAPTURING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    undo_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
