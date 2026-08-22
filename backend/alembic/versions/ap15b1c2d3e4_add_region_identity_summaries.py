"""add region identity summaries

Revision ID: ap15b1c2d3e4
Revises: ao15a1b2c3d4
Create Date: 2026-08-21

Phase 15B — Initial Massive Region Generation. Region gains three
generated macro-identity fields (climate/culture/history summaries),
picked from curated pools (app.game.world.content_pools) via a rng
derived from the region's own generation_seed — deterministic per
campaign, never LLM-generated at persistence time. Existing regions get
empty strings (no backfill) rather than NULL, matching the column's own
default="" — they simply predate Phase 15B's identity generation.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ap15b1c2d3e4"
down_revision: Union[str, None] = "ao15a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("regions") as batch_op:
        batch_op.add_column(
            sa.Column("climate_summary", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("cultural_summary", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("historical_summary", sa.String(), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("regions") as batch_op:
        batch_op.drop_column("historical_summary")
        batch_op.drop_column("cultural_summary")
        batch_op.drop_column("climate_summary")
