"""add quest participation

Revision ID: s12k1l2m3n4o
Revises: r12i1j2k3l4m
Create Date: 2026-08-21

Phase 12K — Quest Participation & Competition: a Quest declares how many
characters may actively pursue it at once — OPEN (unlimited, the prior
implicit behavior), CLAIMABLE (one at a time), LIMITED (up to capacity),
or OFFICIAL_BOUNTY (unlimited, stays available until resolved). Existing
rows default to OPEN — unchanged behavior for every quest created before
this migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s12k1l2m3n4o"
down_revision: Union[str, None] = "r12i1j2k3l4m"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quests",
        sa.Column("participation_type", sa.String(), nullable=False, server_default="OPEN"),
    )
    op.add_column("quests", sa.Column("capacity", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("quests", "capacity")
    op.drop_column("quests", "participation_type")
