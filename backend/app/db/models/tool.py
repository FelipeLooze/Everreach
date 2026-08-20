from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ItemToolProfile(Base):
    """Immutable practical capabilities supplied by a tool definition."""

    __tablename__ = "item_tool_profiles"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id"),
        primary_key=True,
    )
    capabilities_json: Mapped[str] = mapped_column(String, nullable=False)

    item: Mapped["ItemDefinition"] = relationship()
