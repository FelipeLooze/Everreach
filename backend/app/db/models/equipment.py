from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ItemEquipmentProfile(Base):
    """Validated physical positions available to an item definition."""

    __tablename__ = "item_equipment_profiles"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id"),
        primary_key=True,
    )
    allowed_slots_json: Mapped[str] = mapped_column(String, nullable=False)

    item: Mapped["ItemDefinition"] = relationship()
