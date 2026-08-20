from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ItemWeaponProfile(Base):
    """Validated physical capabilities shared by one weapon definition."""

    __tablename__ = "item_weapon_profiles"
    __table_args__ = (
        CheckConstraint(
            "weapon_family IN ('DAGGER', 'KNIFE', 'SWORD', 'AXE', 'HAMMER', "
            "'MACE', 'SPEAR', 'POLEARM', 'BOW', 'CROSSBOW', 'SLING', "
            "'STAFF', 'CLUB')",
            name="ck_item_weapon_family",
        ),
        CheckConstraint(
            "reach IN ('NORMAL', 'LONG', 'RANGED')",
            name="ck_item_weapon_reach",
        ),
        CheckConstraint(
            "hand_requirement IN ('ONE_HAND', 'ONE_OR_TWO_HANDS', 'TWO_HANDS')",
            name="ck_item_weapon_hand_requirement",
        ),
    )

    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id"),
        primary_key=True,
    )
    weapon_family: Mapped[str] = mapped_column(String, nullable=False)
    damage_profiles_json: Mapped[str] = mapped_column(String, nullable=False)
    reach: Mapped[str] = mapped_column(String, nullable=False)
    hand_requirement: Mapped[str] = mapped_column(String, nullable=False)

    item: Mapped["ItemDefinition"] = relationship()
