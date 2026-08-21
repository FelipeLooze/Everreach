from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class LocalSupplyLevel(Base):
    """Phase 14H — a restrained local supply/demand indicator, one row
    per (location, item definition). 100 is baseline/normal; lower means
    a shortage (prices rise), higher means a surplus (prices fall).
    Deliberately not tracked per-item-instance or per-continent — this is
    the settlement/local-market abstraction the spec asks for, reusing
    the existing Location model (Phase 4) rather than a new "market"
    concept, since Phase 14I (Local Economy) hasn't defined a richer
    settlement entity yet."""

    __tablename__ = "local_supply_levels"
    __table_args__ = (
        UniqueConstraint("location_id", "item_definition_id", name="uq_local_supply_location_item"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("supply"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    item_definition_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    supply_index: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    updated_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
