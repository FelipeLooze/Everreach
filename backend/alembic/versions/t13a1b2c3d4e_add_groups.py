"""add groups

Revision ID: t13a1b2c3d4e
Revises: s12k1l2m3n4o
Create Date: 2026-08-21

Phase 13A — Group Foundation: a smaller, often temporary, agency-driven
social grouping — distinct from SimulatedPlayerGroup (Phase 7, an
internal world-simulation mechanism with no concept of consent) and from
the future Organization (Phase 13C+, persistent infrastructure). Member
type reuses CombatActorType's CHARACTER/NPC/SIMULATED_PLAYER vocabulary.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t13a1b2c3d4e"
down_revision: Union[str, None] = "s12k1l2m3n4o"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("group_type", sa.String(), nullable=False, server_default="OTHER"),
        sa.Column("purpose", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("leader_type", sa.String(), nullable=True),
        sa.Column("leader_id", sa.String(), nullable=True),
        sa.Column("location_id", sa.String(), nullable=True),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "group_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("member_type", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(), nullable=False),
        sa.Column("joined_world_minute", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("left_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "member_type", "member_id", name="uq_group_member"),
    )


def downgrade() -> None:
    op.drop_table("group_members")
    op.drop_table("groups")
