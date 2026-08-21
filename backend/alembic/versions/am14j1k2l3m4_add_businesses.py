"""add businesses

Revision ID: am14j1k2l3m4
Revises: al14i1j2k3l4
Create Date: 2026-08-21

Phase 14J — Businesses & Ownership: ownership structure, separate from
Phase 14G's Shop (retail behavior). owner_type is EconomicActorType (an
Organization may own a business); operator (who runs it day to day) is
optional and separate from the owner.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "am14j1k2l3m4"
down_revision: Union[str, None] = "al14i1j2k3l4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("business_type", sa.String(), nullable=False, server_default="OTHER"),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("operator_type", sa.String(), nullable=True),
        sa.Column("operator_id", sa.String(), nullable=True),
        sa.Column("location_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("founded_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("businesses")
