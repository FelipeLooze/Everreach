"""add authoritative consumables and loot

Revision ID: n10n1o2p3q4r5
Revises: m0k1l2m3n4o5
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "n10n1o2p3q4r5"
down_revision: str | None = "m0k1l2m3n4o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "item_consumable_profiles",
        sa.Column("item_definition_id", sa.String(), nullable=False),
        sa.Column("hp_restore", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mana_restore", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stamina_restore", sa.Float(), nullable=False, server_default="0"),
        sa.Column("hunger_restore", sa.Float(), nullable=False, server_default="0"),
        sa.Column("thirst_restore", sa.Float(), nullable=False, server_default="0"),
        sa.Column("use_minutes", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("hp_restore >= 0", name="ck_consumable_hp_nonnegative"),
        sa.CheckConstraint("mana_restore >= 0", name="ck_consumable_mana_nonnegative"),
        sa.CheckConstraint("stamina_restore >= 0", name="ck_consumable_stamina_nonnegative"),
        sa.CheckConstraint("hunger_restore >= 0", name="ck_consumable_hunger_nonnegative"),
        sa.CheckConstraint("thirst_restore >= 0", name="ck_consumable_thirst_nonnegative"),
        sa.CheckConstraint("use_minutes >= 0", name="ck_consumable_minutes_nonnegative"),
        sa.ForeignKeyConstraint(["item_definition_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("item_definition_id"),
    )
    op.create_table(
        "item_consumption_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("item_instance_id", sa.String(), nullable=False),
        sa.Column("item_definition_id", sa.String(), nullable=False),
        sa.Column("effects_json", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["item_definition_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_key"),
    )
    op.create_table(
        "loot_tables",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("key"),
    )
    op.create_table(
        "loot_table_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("loot_table_id", sa.String(), nullable=False),
        sa.Column("item_definition_id", sa.String(), nullable=False),
        sa.Column("drop_chance", sa.Float(), nullable=False),
        sa.Column("min_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("drop_chance >= 0 AND drop_chance <= 1", name="ck_loot_chance"),
        sa.CheckConstraint("min_quantity > 0", name="ck_loot_min_quantity"),
        sa.CheckConstraint("max_quantity >= min_quantity", name="ck_loot_quantity_range"),
        sa.ForeignKeyConstraint(["loot_table_id"], ["loot_tables.id"]),
        sa.ForeignKeyConstraint(["item_definition_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("loot_table_id", "item_definition_id", name="uq_loot_table_item"),
    )
    op.create_table(
        "actor_loot_profiles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("loot_table_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["loot_table_id"], ["loot_tables.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "actor_type", "actor_id", name="uq_actor_loot_profile"),
    )
    op.create_table(
        "loot_resolutions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("source_actor_type", sa.String(), nullable=False),
        sa.Column("source_actor_id", sa.String(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("luck_value", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_key"),
        sa.UniqueConstraint("campaign_id", "source_actor_type", "source_actor_id", name="uq_loot_source_once"),
    )


def downgrade() -> None:
    for table in ("loot_resolutions", "actor_loot_profiles", "loot_table_entries", "loot_tables", "item_consumption_records", "item_consumable_profiles"):
        op.drop_table(table)
