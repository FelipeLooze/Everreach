"""add organization roles and members

Revision ID: y13f1g2h3i4j
Revises: x13e1f2g3h4i
Create Date: 2026-08-21

Phase 13F — Roles, Ranks & Permissions: OrganizationRole belongs to
exactly one organization — there is no shared global rank list reused
across every organization. OrganizationMember is one row per membership
stint (not per member), so an expulsion followed by a later rejoin stay
two distinct preserved historical facts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y13f1g2h3i4j"
down_revision: Union[str, None] = "x13e1f2g3h4i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_roles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("rank_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("permissions_json", sa.String(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "organization_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("member_type", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("joined_world_minute", sa.Integer(), nullable=False),
        sa.Column("left_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["organization_roles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("organization_members")
    op.drop_table("organization_roles")
