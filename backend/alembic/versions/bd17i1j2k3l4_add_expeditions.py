"""add expeditions

Revision ID: bd17i1j2k3l4
Revises: bc17g1h2i3j4
Create Date: 2026-08-22

Phase 17I — Expeditions. New `expeditions` table: a thin overlay on
Group (Phase 13A's GroupType.EXPEDITION) — group_id, target
(subject_kind/entity_id, optional), origin, and lifecycle status. No
changes to any existing table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "bd17i1j2k3l4"
down_revision: Union[str, None] = "bc17g1h2i3j4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expeditions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("group_id", sa.String(), sa.ForeignKey("groups.id"), nullable=False, unique=True),
        sa.Column("purpose", sa.String(), nullable=False, server_default=""),
        sa.Column("target_subject_kind", sa.String(), nullable=True),
        sa.Column("target_entity_id", sa.String(), nullable=True),
        sa.Column("origin_location_id", sa.String(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PLANNED"),
        sa.Column("started_world_minute", sa.Integer(), nullable=True),
        sa.Column("resolved_world_minute", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("expeditions")
