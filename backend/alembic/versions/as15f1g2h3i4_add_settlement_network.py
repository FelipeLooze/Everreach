"""add settlement network

Revision ID: as15f1g2h3i4
Revises: ar15d1e2f3g4
Create Date: 2026-08-21

Phase 15F — Settlement Network. New `settlements` table: a thin overlay
on Location (never a parallel geography system) adding settlement_type/
profile/population_tier. Location gains materialization_tier (Three-Tier
Materialization Model: 1 = fully generated now, 2 = named stub filled in
later, 3 = interior/micro-detail on demand). Existing locations default
to tier 1 (they were all fully authored already).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "as15f1g2h3i4"
down_revision: Union[str, None] = "ar15d1e2f3g4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settlements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "location_id", sa.String(), sa.ForeignKey("locations.id"), nullable=False, unique=True
        ),
        sa.Column("settlement_type", sa.String(), nullable=False, server_default="VILLAGE"),
        sa.Column("profile", sa.String(), nullable=False, server_default=""),
        sa.Column("population_tier", sa.Integer(), nullable=False, server_default="1"),
    )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.add_column(
            sa.Column("materialization_tier", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_column("materialization_tier")

    op.drop_table("settlements")
