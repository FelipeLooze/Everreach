"""add boundary routes

Revision ID: ay16d1e2f3g4
Revises: ax16c1d2e3f4
Create Date: 2026-08-22

Phase 16D — Cross-Region Routes. New `boundary_routes` table: the
possible ways through a RegionalBoundary (usually 2-3, with genuinely
different tradeoffs), kept separate from the boundary/barrier itself
("BOUNDARY != ROUTE"). No changes to any existing table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ay16d1e2f3g4"
down_revision: Union[str, None] = "ax16c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "boundary_routes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("boundary_id", sa.String(), sa.ForeignKey("regional_boundaries.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("terrain", sa.String(), nullable=False, server_default=""),
        sa.Column("origin_location_id", sa.String(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("destination_location_id", sa.String(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("estimated_distance", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("danger_hint", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("political_control", sa.String(), nullable=False, server_default=""),
        sa.Column("is_publicly_known", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("knowledge_fact_key", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("boundary_routes")
