"""add region materialization requests

Revision ID: av16a1b2c3d4
Revises: au15l1m2n3o4
Create Date: 2026-08-22

Phase 16A — Region Materialization Triggers. New
`region_materialization_requests` table: an authoritative record that a
neighboring Region needs to exist, created by whichever system determined
so (player exploration, a simulated character, an organization, a quest/
event, the economy, or world history/Canon) — never generated implicitly
just because the protagonist reached a map edge. No changes to any
existing table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "av16a1b2c3d4"
down_revision: Union[str, None] = "au15l1m2n3o4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "region_materialization_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("source_region_id", sa.String(), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("requested_by_type", sa.String(), nullable=False),
        sa.Column("requested_by_id", sa.String(), nullable=False, server_default=""),
        sa.Column("reason", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("requested_world_minute", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fulfilled_region_id", sa.String(), sa.ForeignKey("regions.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("region_materialization_requests")
