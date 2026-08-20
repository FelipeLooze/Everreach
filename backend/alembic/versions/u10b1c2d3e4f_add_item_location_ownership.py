"""add authoritative item location and ownership

Revision ID: u10b1c2d3e4f
Revises: t10a1b2c3d4e
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u10b1c2d3e4f"
down_revision: Union[str, None] = "t10a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.add_column(sa.Column("campaign_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "location_type",
                sa.String(),
                nullable=False,
                server_default="UNPLACED",
            )
        )
        batch_op.add_column(sa.Column("location_ref", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "owner_type",
                sa.String(),
                nullable=False,
                server_default="NONE",
            )
        )
        batch_op.add_column(sa.Column("owner_ref", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_item_instance_campaign",
            "campaigns",
            ["campaign_id"],
            ["id"],
        )

    # Convert the original character inventory into physical instances. This
    # is the one-time bridge; inventory_items is removed below so location has
    # exactly one authoritative representation after the migration.
    op.execute(
        "INSERT INTO item_instances "
        "(id, definition_id, quantity, campaign_id, location_type, location_ref, owner_type, owner_ref) "
        "SELECT 'item_instance_' || inventory_items.id, inventory_items.item_id, "
        "inventory_items.quantity, characters.campaign_id, "
        "CASE WHEN inventory_items.equipped = 1 THEN 'CHARACTER_EQUIPPED' ELSE 'CHARACTER' END, "
        "inventory_items.character_id, 'CHARACTER', inventory_items.character_id "
        "FROM inventory_items JOIN characters "
        "ON characters.id = inventory_items.character_id"
    )
    op.drop_table("inventory_items")

    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.create_check_constraint(
            "ck_item_instance_location_ref",
            "(location_type = 'UNPLACED' AND location_ref IS NULL) OR "
            "(location_type <> 'UNPLACED' AND location_ref IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_item_instance_location_type",
            "location_type IN ('UNPLACED', 'CHARACTER', 'CHARACTER_EQUIPPED', "
            "'NPC', 'WORLD_LOCATION', 'CONTAINER')",
        )
        batch_op.create_check_constraint(
            "ck_item_instance_owner_ref",
            "(owner_type = 'NONE' AND owner_ref IS NULL) OR "
            "(owner_type <> 'NONE' AND owner_ref IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_item_instance_owner_type",
            "owner_type IN ('NONE', 'CHARACTER', 'NPC')",
        )
        batch_op.create_index(
            "ix_item_instance_campaign_location",
            ["campaign_id", "location_type", "location_ref"],
        )
        batch_op.create_index(
            "ix_item_instance_campaign_owner",
            ["campaign_id", "owner_type", "owner_ref"],
        )


def downgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("equipped", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO inventory_items (id, character_id, item_id, quantity, equipped) "
        "SELECT 'inv_restored_' || id, location_ref, definition_id, quantity, "
        "CASE WHEN location_type = 'CHARACTER_EQUIPPED' THEN 1 ELSE 0 END "
        "FROM item_instances WHERE location_type IN ('CHARACTER', 'CHARACTER_EQUIPPED')"
    )
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.drop_index("ix_item_instance_campaign_owner")
        batch_op.drop_index("ix_item_instance_campaign_location")
        batch_op.drop_constraint("ck_item_instance_owner_ref", type_="check")
        batch_op.drop_constraint("ck_item_instance_owner_type", type_="check")
        batch_op.drop_constraint("ck_item_instance_location_ref", type_="check")
        batch_op.drop_constraint("ck_item_instance_location_type", type_="check")
        batch_op.drop_constraint("fk_item_instance_campaign", type_="foreignkey")
        batch_op.drop_column("owner_ref")
        batch_op.drop_column("owner_type")
        batch_op.drop_column("location_ref")
        batch_op.drop_column("location_type")
        batch_op.drop_column("campaign_id")
