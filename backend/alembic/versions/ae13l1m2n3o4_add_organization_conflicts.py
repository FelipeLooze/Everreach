"""add organization conflicts

Revision ID: ae13l1m2n3o4
Revises: ad13k1l2m3n4
Create Date: 2026-08-21

Phase 13L — Conflicts & Politics: a real, named situation with a cause
(reasons), never a bare relation=-80. Not tied to exactly two
organizations — INTERNAL_SCHISM may involve just one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ae13l1m2n3o4"
down_revision: Union[str, None] = "ad13k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_conflicts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("conflict_type", sa.String(), nullable=False),
        sa.Column("reasons", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("started_world_minute", sa.Integer(), nullable=False),
        sa.Column("resolved_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "organization_conflict_participants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conflict_id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["conflict_id"], ["organization_conflicts.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conflict_id", "organization_id", name="uq_conflict_participant"),
    )


def downgrade() -> None:
    op.drop_table("organization_conflict_participants")
    op.drop_table("organization_conflicts")
