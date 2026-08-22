"""add regional boundaries

Revision ID: aw16b1c2d3e4
Revises: av16a1b2c3d4
Create Date: 2026-08-22

Phase 16B — Regional Boundary Foundation. New `regional_boundaries`
table: the world conditions separating a materialized Region from
whatever lies beyond it (never a map line, never a level gate).
destination_region_id stays NULL until a later subphase actually
materializes the neighboring Region. No changes to any existing table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aw16b1c2d3e4"
down_revision: Union[str, None] = "av16a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "regional_boundaries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("source_region_id", sa.String(), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("destination_region_id", sa.String(), sa.ForeignKey("regions.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("boundary_side", sa.String(), nullable=False, server_default=""),
        sa.Column("anchor_subregion_id", sa.String(), sa.ForeignKey("subregions.id"), nullable=False),
        sa.Column("frontier_location_id", sa.String(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("generation_seed", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("regional_boundaries")
