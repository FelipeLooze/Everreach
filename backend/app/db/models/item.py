from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.db.base import Base


class ItemDefinition(Base):
    """The shared mechanical concept of an item, not a physical object."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("item"))
    key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, default="MISC", nullable=False)
    instance_mode: Mapped[str] = mapped_column(
        String,
        default="STACKABLE",
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String, default="")
    # Legacy extension field. Phase 10 does not treat arbitrary values stored
    # here as mechanical authority; category services must use validated data.
    stats_json: Mapped[str] = mapped_column(String, default="{}")

    instances: Mapped[list["ItemInstance"]] = relationship(
        back_populates="definition"
    )


class ItemInstance(Base):
    """One physical object or one interchangeable stack existing in the world."""

    __tablename__ = "item_instances"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_item_instance_quantity_positive",
        ),
        Index("ix_item_instance_definition", "definition_id"),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("item_instance"),
    )
    definition_id: Mapped[str] = mapped_column(
        ForeignKey("items.id"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    definition: Mapped["ItemDefinition"] = relationship(back_populates="instances")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("inv"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    equipped: Mapped[bool] = mapped_column(Boolean, default=False)


# Compatibility name for Phase 9 call sites. New Phase 10 code should say
# ItemDefinition explicitly so definition and physical instance cannot be confused.
Item = ItemDefinition
