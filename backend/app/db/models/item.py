from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("item"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, default="misc")
    description: Mapped[str] = mapped_column(String, default="")
    stats_json: Mapped[str] = mapped_column(String, default="{}")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("inv"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    equipped: Mapped[bool] = mapped_column(Boolean, default=False)
