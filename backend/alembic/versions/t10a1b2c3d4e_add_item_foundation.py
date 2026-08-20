"""add item definitions and physical instances

Revision ID: t10a1b2c3d4e
Revises: s9l1m2n3o4p5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t10a1b2c3d4e"
down_revision: Union[str, None] = "s9l1m2n3o4p5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("key", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "instance_mode",
                sa.String(),
                nullable=False,
                server_default="STACKABLE",
            )
        )

    # Existing IDs are the only guaranteed stable unique identifiers. Keep
    # them as migration keys instead of guessing semantic keys from names.
    op.execute("UPDATE items SET key = id WHERE key IS NULL")
    op.execute(
        "UPDATE items SET type = CASE UPPER(type) "
        "WHEN 'MISC' THEN 'MISC' "
        "WHEN 'MATERIAL' THEN 'MATERIAL' "
        "WHEN 'CURRENCY' THEN 'CURRENCY' "
        "WHEN 'AMMUNITION' THEN 'AMMUNITION' "
        "WHEN 'CONSUMABLE' THEN 'CONSUMABLE' "
        "WHEN 'WEAPON' THEN 'WEAPON' "
        "WHEN 'ARMOR' THEN 'ARMOR' "
        "WHEN 'TOOL' THEN 'TOOL' "
        "WHEN 'CONTAINER' THEN 'CONTAINER' "
        "WHEN 'QUEST' THEN 'QUEST' "
        "ELSE 'MISC' END"
    )
    # Phase 9 combat profiles already prove that these definitions describe
    # individually significant equipment rather than interchangeable stacks.
    op.execute(
        "UPDATE items SET instance_mode = 'UNIQUE' "
        "WHERE id IN (SELECT item_id FROM item_combat_profiles)"
    )

    with op.batch_alter_table("items") as batch_op:
        batch_op.alter_column("key", existing_type=sa.String(), nullable=False)
        batch_op.create_unique_constraint("uq_item_definition_key", ["key"])

    op.create_table(
        "item_instances",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("definition_id", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_item_instance_quantity_positive",
        ),
        sa.ForeignKeyConstraint(["definition_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_item_instance_definition",
        "item_instances",
        ["definition_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_item_instance_definition", table_name="item_instances")
    op.drop_table("item_instances")
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_constraint("uq_item_definition_key", type_="unique")
        batch_op.drop_column("instance_mode")
        batch_op.drop_column("key")
