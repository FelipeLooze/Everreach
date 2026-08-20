from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.db.base import Base


class ItemDefinition(Base):
    """The shared mechanical concept of an item, not a physical object."""

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint("base_weight >= 0", name="ck_item_base_weight_nonnegative"),
    )

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
    base_weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
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
        CheckConstraint(
            "(location_type = 'UNPLACED' AND location_ref IS NULL) OR "
            "(location_type <> 'UNPLACED' AND location_ref IS NOT NULL)",
            name="ck_item_instance_location_ref",
        ),
        CheckConstraint(
            "location_type IN ('UNPLACED', 'CHARACTER', 'CHARACTER_EQUIPPED', "
            "'NPC', 'WORLD_LOCATION', 'CONTAINER')",
            name="ck_item_instance_location_type",
        ),
        CheckConstraint(
            "(owner_type = 'NONE' AND owner_ref IS NULL) OR "
            "(owner_type <> 'NONE' AND owner_ref IS NOT NULL)",
            name="ck_item_instance_owner_ref",
        ),
        CheckConstraint(
            "owner_type IN ('NONE', 'CHARACTER', 'NPC')",
            name="ck_item_instance_owner_type",
        ),
        Index("ix_item_instance_definition", "definition_id"),
        Index(
            "ix_item_instance_campaign_location",
            "campaign_id",
            "location_type",
            "location_ref",
        ),
        Index(
            "ix_item_instance_campaign_owner",
            "campaign_id",
            "owner_type",
            "owner_ref",
        ),
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
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    location_type: Mapped[str] = mapped_column(
        String,
        default="UNPLACED",
        nullable=False,
    )
    location_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_type: Mapped[str] = mapped_column(
        String,
        default="NONE",
        nullable=False,
    )
    owner_ref: Mapped[str | None] = mapped_column(String, nullable=True)

    definition: Mapped["ItemDefinition"] = relationship(back_populates="instances")

    @property
    def item_id(self) -> str:
        """Compatibility accessor for Phase 9 callers."""
        return self.definition_id

    @property
    def character_id(self) -> str | None:
        if self.location_type in {"CHARACTER", "CHARACTER_EQUIPPED"}:
            return self.location_ref
        return None

    @property
    def equipped(self) -> bool:
        return self.location_type == "CHARACTER_EQUIPPED"


# Compatibility name for Phase 9 call sites. New Phase 10 code should say
# ItemDefinition explicitly so definition and physical instance cannot be confused.
Item = ItemDefinition
