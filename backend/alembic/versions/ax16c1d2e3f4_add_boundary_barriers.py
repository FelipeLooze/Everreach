"""add boundary barriers

Revision ID: ax16c1d2e3f4
Revises: aw16b1c2d3e4
Create Date: 2026-08-22

Phase 16C — Boundary Barriers. New `boundary_barriers` table: one or
more concrete hazards (GEOGRAPHICAL/CLIMATIC/ECOLOGICAL/POLITICAL/
LOGISTICAL/MAGICAL) attached to a RegionalBoundary — never a single
difficulty number. No changes to any existing table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ax16c1d2e3f4"
down_revision: Union[str, None] = "aw16b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "boundary_barriers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("boundary_id", sa.String(), sa.ForeignKey("regional_boundaries.id"), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("boundary_barriers")
