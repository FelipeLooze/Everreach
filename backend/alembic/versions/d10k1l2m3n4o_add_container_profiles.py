"""add authoritative container capacities

Revision ID: d10k1l2m3n4o
Revises: c10j1k2l3m4n
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d10k1l2m3n4o"
down_revision: Union[str, None] = "c10j1k2l3m4n"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_container_profiles",
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("weight_capacity", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "weight_capacity > 0",
            name="ck_item_container_weight_capacity_positive",
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("item_id"),
    )


def downgrade() -> None:
    op.drop_table("item_container_profiles")
