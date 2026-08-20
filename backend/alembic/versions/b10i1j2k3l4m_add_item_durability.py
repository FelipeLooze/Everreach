"""add meaningful item wear and condition

Revision ID: b10i1j2k3l4m
Revises: a10h1i2j3k4l
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b10i1j2k3l4m"
down_revision: Union[str, None] = "a10h1i2j3k4l"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.add_column(sa.Column("durability_current", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("durability_max", sa.Float(), nullable=True))
    op.execute(
        "UPDATE item_instances SET durability_current = 100, durability_max = 100 "
        "WHERE definition_id IN (SELECT id FROM items WHERE type IN "
        "('WEAPON', 'ARMOR', 'TOOL', 'CONTAINER'))"
    )
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.create_check_constraint(
            "ck_item_instance_durability",
            "(durability_current IS NULL AND durability_max IS NULL) OR "
            "(durability_current IS NOT NULL AND durability_max IS NOT NULL "
            "AND durability_max > 0 AND durability_current >= 0 "
            "AND durability_current <= durability_max)",
        )
    op.create_table(
        "item_wear_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("item_instance_id", sa.String(), nullable=False),
        sa.Column("wear_key", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("cause", sa.String(), nullable=False),
        sa.Column("wear_amount", sa.Float(), nullable=False),
        sa.Column("durability_before", sa.Float(), nullable=False),
        sa.Column("durability_after", sa.Float(), nullable=False),
        sa.Column("condition_before", sa.String(), nullable=False),
        sa.Column("condition_after", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.CheckConstraint("wear_amount >= 0", name="ck_item_wear_amount_nonnegative"),
        sa.ForeignKeyConstraint(["item_instance_id"], ["item_instances.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_instance_id", "wear_key", name="uq_item_wear_key"),
    )
    op.create_index(
        "ix_item_wear_instance_time",
        "item_wear_records",
        ["item_instance_id", "created_world_minute"],
    )


def downgrade() -> None:
    op.drop_index("ix_item_wear_instance_time", table_name="item_wear_records")
    op.drop_table("item_wear_records")
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.drop_constraint("ck_item_instance_durability", type_="check")
        batch_op.drop_column("durability_max")
        batch_op.drop_column("durability_current")
