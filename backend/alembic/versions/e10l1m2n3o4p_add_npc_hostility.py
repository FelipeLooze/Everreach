"""add npc hostility meter

Revision ID: e10l1m2n3o4p
Revises: d10k1l2m3n4o
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e10l1m2n3o4p"
down_revision: Union[str, None] = "d10k1l2m3n4o"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "npcs",
        sa.Column("hostility", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("npcs", "hostility")
