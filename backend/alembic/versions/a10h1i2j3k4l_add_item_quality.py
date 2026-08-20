"""add craftsmanship quality to item instances

Revision ID: a10h1i2j3k4l
Revises: z10g1h2i3j4k
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a10h1i2j3k4l"
down_revision: Union[str, None] = "z10g1h2i3j4k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.add_column(
            sa.Column(
                "quality",
                sa.String(),
                nullable=False,
                server_default="STANDARD",
            )
        )
        batch_op.create_check_constraint(
            "ck_item_instance_quality",
            "quality IN ('CRUDE', 'POOR', 'STANDARD', 'GOOD', 'EXCELLENT', "
            "'MASTERWORK')",
        )


def downgrade() -> None:
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.drop_constraint("ck_item_instance_quality", type_="check")
        batch_op.drop_column("quality")
