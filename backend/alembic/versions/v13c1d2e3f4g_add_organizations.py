"""add organizations

Revision ID: v13c1d2e3f4g
Revises: u13b1c2d3e4f
Create Date: 2026-08-21

Phase 13C — Organization Foundation: one general, extensible model for
every persistent social entity (guild, church, military order, criminal
network...) rather than a separate table per type. Foundation only — no
membership, roles, reputation, relationships, goals or resources yet.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v13c1d2e3f4g"
down_revision: Union[str, None] = "u13b1c2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("organization_type", sa.String(), nullable=False, server_default="OTHER"),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("visibility", sa.String(), nullable=False, server_default="PUBLIC"),
        sa.Column("headquarters_location_id", sa.String(), nullable=True),
        sa.Column("founder_type", sa.String(), nullable=True),
        sa.Column("founder_id", sa.String(), nullable=True),
        sa.Column("founded_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["headquarters_location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("organizations")
