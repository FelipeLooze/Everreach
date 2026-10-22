from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ItemConsumableProfile(Base):
    """Validated effects for one consumable definition.

    Free-form item metadata is deliberately not mechanical authority.
    """

    __tablename__ = "item_consumable_profiles"
    __table_args__ = (
        CheckConstraint("hp_restore >= 0", name="ck_consumable_hp_nonnegative"),
        CheckConstraint("mana_restore >= 0", name="ck_consumable_mana_nonnegative"),
        CheckConstraint("stamina_restore >= 0", name="ck_consumable_stamina_nonnegative"),
        CheckConstraint("hunger_restore >= 0", name="ck_consumable_hunger_nonnegative"),
        CheckConstraint("thirst_restore >= 0", name="ck_consumable_thirst_nonnegative"),
        CheckConstraint("use_minutes >= 0", name="ck_consumable_minutes_nonnegative"),
    )

    item_definition_id: Mapped[str] = mapped_column(
        ForeignKey("items.id"), primary_key=True
    )
    hp_restore: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    mana_restore: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    stamina_restore: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    hunger_restore: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    thirst_restore: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    use_minutes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ItemConsumptionRecord(Base):
    __tablename__ = "item_consumption_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    action_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    item_instance_id: Mapped[str] = mapped_column(String, nullable=False)
    item_definition_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    effects_json: Mapped[str] = mapped_column(String, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
