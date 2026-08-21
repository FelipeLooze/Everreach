"""add organization relations

Revision ID: aa13h1i2j3k4
Revises: z13g1h2i3j4k
Create Date: 2026-08-21

Phase 13H — Organization Relationships: one row per relationship fact,
not per organization pair — multiple relation_type rows may coexist and
be ACTIVE at once between the same two organizations (e.g. TRADE_PARTNER
and COMPETITOR simultaneously). Ended relations are never deleted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aa13h1i2j3k4"
down_revision: Union[str, None] = "z13g1h2i3j4k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_relations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_a_id", sa.String(), nullable=False),
        sa.Column("organization_b_id", sa.String(), nullable=False),
        sa.Column("relation_type", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("established_world_minute", sa.Integer(), nullable=False),
        sa.Column("ended_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["organization_a_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["organization_b_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("organization_relations")
