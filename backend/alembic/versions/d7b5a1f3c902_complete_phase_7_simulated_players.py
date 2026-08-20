"""complete phase 7 simulated players

Revision ID: d7b5a1f3c902
Revises: c4a6d9e217bf
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d7b5a1f3c902"
down_revision: Union[str, None] = "c4a6d9e217bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.add_column(
            sa.Column("xp", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "risk_tolerance",
                sa.String(),
                nullable=False,
                server_default="BALANCED",
            )
        )

    op.create_table(
        "simulated_player_skills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("simulated_player_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("mastery", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["simulated_player_id"], ["simulated_players.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "simulated_player_id",
            "name",
            name="uq_simulated_player_skill_name",
        ),
    )
    op.create_table(
        "simulated_player_relationships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("first_player_id", sa.String(), nullable=False),
        sa.Column("second_player_id", sa.String(), nullable=False),
        sa.Column("familiarity", sa.Integer(), nullable=False),
        sa.Column("trust", sa.Integer(), nullable=False),
        sa.Column("affinity", sa.Integer(), nullable=False),
        sa.Column("last_interaction_minute", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["first_player_id"], ["simulated_players.id"]),
        sa.ForeignKeyConstraint(["second_player_id"], ["simulated_players.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "first_player_id",
            "second_player_id",
            name="uq_simulated_player_relationship_pair",
        ),
    )
    op.create_index(
        "ix_simulated_player_relationship_campaign",
        "simulated_player_relationships",
        ["campaign_id", "first_player_id", "second_player_id"],
        unique=False,
    )
    op.create_table(
        "simulated_player_groups",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("leader_id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=False),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["leader_id"], ["simulated_players.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_simulated_player_group_campaign_status",
        "simulated_player_groups",
        ["campaign_id", "status"],
        unique=False,
    )
    op.create_table(
        "simulated_player_group_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("simulated_player_id", sa.String(), nullable=False),
        sa.Column("joined_world_minute", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("left_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["simulated_player_groups.id"]),
        sa.ForeignKeyConstraint(["simulated_player_id"], ["simulated_players.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id",
            "simulated_player_id",
            name="uq_simulated_player_group_member",
        ),
    )
    op.create_index(
        "ix_simulated_player_active_group_membership",
        "simulated_player_group_members",
        ["simulated_player_id", "active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_simulated_player_active_group_membership",
        table_name="simulated_player_group_members",
    )
    op.drop_table("simulated_player_group_members")
    op.drop_index(
        "ix_simulated_player_group_campaign_status",
        table_name="simulated_player_groups",
    )
    op.drop_table("simulated_player_groups")
    op.drop_index(
        "ix_simulated_player_relationship_campaign",
        table_name="simulated_player_relationships",
    )
    op.drop_table("simulated_player_relationships")
    op.drop_table("simulated_player_skills")
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.drop_column("risk_tolerance")
        batch_op.drop_column("xp")
