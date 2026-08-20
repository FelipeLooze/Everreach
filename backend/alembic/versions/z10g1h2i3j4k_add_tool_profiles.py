"""add authoritative tool capabilities

Revision ID: z10g1h2i3j4k
Revises: y10f1g2h3i4j
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "z10g1h2i3j4k"
down_revision: Union[str, None] = "y10f1g2h3i4j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_tool_profiles",
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("capabilities_json", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("item_id"),
    )


def downgrade() -> None:
    op.drop_table("item_tool_profiles")
