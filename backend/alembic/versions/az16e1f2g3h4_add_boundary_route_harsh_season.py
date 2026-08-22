"""add boundary route harsh season

Revision ID: az16e1f2g3h4
Revises: ay16d1e2f3g4
Create Date: 2026-08-22

Phase 16E — Seasonal & Temporal Accessibility. Adds harsh_season to
boundary_routes — the one season a route is roughest in. Accessibility
itself (OPEN/RISKY/NEARLY_IMPASSABLE) is always derived on demand from
this plus the current in-world season, never stored as a boolean.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "az16e1f2g3h4"
down_revision: Union[str, None] = "ay16d1e2f3g4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "boundary_routes",
        sa.Column("harsh_season", sa.String(), nullable=False, server_default="WINTER"),
    )


def downgrade() -> None:
    op.drop_column("boundary_routes", "harsh_season")
