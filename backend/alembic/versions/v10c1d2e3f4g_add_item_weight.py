"""add item weight for encumbrance

Revision ID: v10c1d2e3f4g
Revises: u10b1c2d3e4f
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "v10c1d2e3f4g"
down_revision: Union[str, None] = "u10b1c2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(
            sa.Column("base_weight", sa.Float(), nullable=False, server_default="0.0")
        )
        batch_op.create_check_constraint(
            "ck_item_base_weight_nonnegative",
            "base_weight >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_constraint("ck_item_base_weight_nonnegative", type_="check")
        batch_op.drop_column("base_weight")
