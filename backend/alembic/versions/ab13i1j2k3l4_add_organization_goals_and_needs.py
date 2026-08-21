"""add organization goals and needs

Revision ID: ab13i1j2k3l4
Revises: aa13h1i2j3k4
Create Date: 2026-08-21

Phase 13I — Organization Goals & Needs: a Goal is the qualitative "why"
(free text — too varied for a fixed enum); a Need is the concrete "what
it takes," with a structured category since Phase 13M will route needs
toward Notices/jobs by kind, optionally in service of a Goal.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ab13i1j2k3l4"
down_revision: Union[str, None] = "aa13h1i2j3k4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_goals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "organization_needs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("goal_id", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["goal_id"], ["organization_goals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("organization_needs")
    op.drop_table("organization_goals")
