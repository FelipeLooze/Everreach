"""add group invites

Revision ID: u13b1c2d3e4f
Revises: t13a1b2c3d4e
Create Date: 2026-08-21

Phase 13B — Group Membership & Temporary Groups: a GroupInvite is a
pending social proposal, never assumed accepted — invite/join/leave/
remove/leadership change all become authoritative, agency-preserving
actions instead of silent narration side effects.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u13b1c2d3e4f"
down_revision: Union[str, None] = "t13a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_invites",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("inviter_type", sa.String(), nullable=False),
        sa.Column("inviter_id", sa.String(), nullable=False),
        sa.Column("invited_type", sa.String(), nullable=False),
        sa.Column("invited_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.Column("resolved_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("group_invites")
