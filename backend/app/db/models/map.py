from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from datetime import UTC, datetime

from app.core.ids import generate_id
from app.db.base import Base


class Map(Base):
    """
    Phase 17G — a physical map is a real Phase 10 Item (ItemType.MAP,
    always instance_mode=UNIQUE — two maps are never interchangeable
    even if they cover the same place, since their content can differ).
    This is a thin overlay, exactly like Settlement overlays Location:
    the ItemInstance already handles ownership/location/durability;
    this table only adds what's specific to being a map.

    content_json is a frozen JSON snapshot of a CartographicSurvey
    (app.game.knowledge.cartography) taken once, at creation time — it
    is NEVER a live reference back to KnowledgeFact/KnowledgeKnower.
    "MAP DATA != WORLD TRUTH" (spec): if the world changes after this
    row is written, this map's content does not — see
    app.game.knowledge.maps for how staleness/accuracy get evaluated
    against current knowledge without ever mutating this snapshot.
    """

    __tablename__ = "maps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("map"))
    item_instance_id: Mapped[str] = mapped_column(ForeignKey("item_instances.id"), nullable=False, unique=True)

    subject_kind: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)

    creator_type: Mapped[str] = mapped_column(String, nullable=False)
    creator_id: Mapped[str] = mapped_column(String, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

    content_json: Mapped[str] = mapped_column(String, nullable=False)
