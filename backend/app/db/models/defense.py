from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import generate_id
from app.db.base import Base


class ItemCombatProfile(Base):
    """Validated defensive mechanics for an equippable catalog item."""

    __tablename__ = "item_combat_profiles"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id"),
        primary_key=True,
    )
    slot: Mapped[str] = mapped_column(String, nullable=False)
    armor_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resistances_json: Mapped[str] = mapped_column(String, default="{}", nullable=False)

    item: Mapped["Item"] = relationship()


class ActorCombatDefense(Base):
    """Optional innate armor and resistance for one concrete combat actor."""

    __tablename__ = "actor_combat_defenses"
    __table_args__ = (
        UniqueConstraint(
            "actor_type",
            "actor_id",
            name="uq_actor_combat_defense_identity",
        ),
        Index(
            "ix_actor_combat_defense_identity",
            "actor_type",
            "actor_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("defense"),
    )
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    armor_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resistances_json: Mapped[str] = mapped_column(String, default="{}", nullable=False)
