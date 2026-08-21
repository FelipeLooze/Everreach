"""add organization reputation

Revision ID: z13g1h2i3j4k
Revises: y13f1g2h3i4j
Create Date: 2026-08-21

Phase 13G — Reputation: append-only, explainable reputation records
(organization's opinion of a character/NPC, never personal relationship —
that stays app.db.models.relationship). A raw score is derived by summing
deltas; it is never the sole source of truth on its own.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z13g1h2i3j4k"
down_revision: Union[str, None] = "y13f1g2h3i4j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_reputation_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("organization_reputation_records")
