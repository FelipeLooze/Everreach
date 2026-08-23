from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class MapAnnotation(Base):
    """Phase 20J — Player Map Annotations.

    "PLAYER NOTE != WORLD TRUTH" (spec): this table is deliberately not
    Knowledge, not a KnowledgeFact, not read by anything Canon-facing —
    writing "Dragon nest." here never creates a dragon nest. It belongs
    to exactly the character who wrote it and is never visible to
    anyone else's Map View.

    Targets a Location (the simplest of the spec's listed targets —
    "coordinate/area... route... free map position" are explicitly
    allowed future extensions, not required for the initial
    implementation) that the character can currently see on their own
    Map View at creation time (app.game.map.annotations.create_annotation
    enforces this) — an annotation can never be pinned to a location the
    character has no legitimate reason to know about.
    """

    __tablename__ = "map_annotations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("annotation"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
