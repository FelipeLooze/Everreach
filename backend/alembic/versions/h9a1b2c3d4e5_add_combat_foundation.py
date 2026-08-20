"""add combat encounter foundation

Revision ID: h9a1b2c3d4e5
Revises: g8k1a2b3c4d5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "h9a1b2c3d4e5"
down_revision: Union[str, None] = "g8k1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "combat_encounters",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("started_world_minute", sa.Integer(), nullable=False),
        sa.Column("ended_world_minute", sa.Integer(), nullable=True),
        sa.Column("end_reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_combat_encounter_campaign_status",
        "combat_encounters",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_combat_encounter_location_status",
        "combat_encounters",
        ["location_id", "status"],
    )
    op.create_table(
        "combat_participants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("side_key", sa.String(), nullable=False),
        sa.Column("range_band", sa.String(), nullable=False),
        sa.Column("awareness", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("joined_world_minute", sa.Integer(), nullable=False),
        sa.Column("left_world_minute", sa.Integer(), nullable=True),
        sa.Column("left_reason", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["encounter_id"],
            ["combat_encounters.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "encounter_id",
            "actor_type",
            "actor_id",
            name="uq_combat_participant_actor",
        ),
    )
    op.create_index(
        "ix_combat_participant_actor_active",
        "combat_participants",
        ["actor_type", "actor_id", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_combat_participant_actor_active",
        table_name="combat_participants",
    )
    op.drop_table("combat_participants")
    op.drop_index(
        "ix_combat_encounter_location_status",
        table_name="combat_encounters",
    )
    op.drop_index(
        "ix_combat_encounter_campaign_status",
        table_name="combat_encounters",
    )
    op.drop_table("combat_encounters")
