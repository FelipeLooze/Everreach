from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class LootTable(Base):
    __tablename__ = "loot_tables"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("loot_table"))
    key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class LootTableEntry(Base):
    __tablename__ = "loot_table_entries"
    __table_args__ = (
        CheckConstraint("drop_chance >= 0 AND drop_chance <= 1", name="ck_loot_chance"),
        CheckConstraint("min_quantity > 0", name="ck_loot_min_quantity"),
        CheckConstraint("max_quantity >= min_quantity", name="ck_loot_quantity_range"),
        UniqueConstraint("loot_table_id", "item_definition_id", name="uq_loot_table_item"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("loot_entry"))
    loot_table_id: Mapped[str] = mapped_column(ForeignKey("loot_tables.id"), nullable=False)
    item_definition_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    drop_chance: Mapped[float] = mapped_column(Float, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ActorLootProfile(Base):
    __tablename__ = "actor_loot_profiles"
    __table_args__ = (
        UniqueConstraint("campaign_id", "actor_type", "actor_id", name="uq_actor_loot_profile"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("loot_profile"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    loot_table_id: Mapped[str] = mapped_column(ForeignKey("loot_tables.id"), nullable=False)


class LootResolution(Base):
    __tablename__ = "loot_resolutions"
    __table_args__ = (
        UniqueConstraint("campaign_id", "source_actor_type", "source_actor_id", name="uq_loot_source_once"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("loot"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    source_actor_type: Mapped[str] = mapped_column(String, nullable=False)
    source_actor_id: Mapped[str] = mapped_column(String, nullable=False)
    action_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    luck_value: Mapped[int] = mapped_column(Integer, nullable=False)
    result_json: Mapped[str] = mapped_column(String, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class CreatureHarvestResolution(Base):
    """One authoritative collection method resolved against one carcass."""

    __tablename__ = "creature_harvest_resolutions"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "source_npc_id",
            "harvest_method",
            name="uq_creature_harvest_source_method",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("harvest")
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False
    )
    # Deliberately not a foreign key: carcass cleanup removes the NPC after
    # two world days while this audit/idempotency record remains.
    source_npc_id: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    species_key: Mapped[str] = mapped_column(String, nullable=False)
    harvest_method: Mapped[str] = mapped_column(String, nullable=False)
    action_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    luck_value: Mapped[int] = mapped_column(Integer, nullable=False)
    result_json: Mapped[str] = mapped_column(String, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
