"""add combat action resolution

Revision ID: j9c1d2e3f4g5
Revises: i9b1c2d3e4f5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "j9c1d2e3f4g5"
down_revision: Union[str, None] = "i9b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "combat_actions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("actor_participant_id", sa.String(), nullable=False),
        sa.Column("target_participant_id", sa.String(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("attack_attribute", sa.String(), nullable=False),
        sa.Column("target_range_band", sa.String(), nullable=False),
        sa.Column("attack_roll", sa.Integer(), nullable=False),
        sa.Column("attack_modifier", sa.Integer(), nullable=False),
        sa.Column("attack_total", sa.Integer(), nullable=False),
        sa.Column("defense_base", sa.Integer(), nullable=False),
        sa.Column("defense_modifier", sa.Integer(), nullable=False),
        sa.Column("defense_total", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["combat_encounters.id"]),
        sa.ForeignKeyConstraint(["turn_id"], ["combat_turns.id"]),
        sa.ForeignKeyConstraint(
            ["actor_participant_id"],
            ["combat_participants.id"],
        ),
        sa.ForeignKeyConstraint(
            ["target_participant_id"],
            ["combat_participants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "encounter_id",
            "action_key",
            name="uq_combat_action_key",
        ),
        sa.UniqueConstraint("turn_id", name="uq_combat_action_turn"),
    )
    op.create_index(
        "ix_combat_action_encounter_time",
        "combat_actions",
        ["encounter_id", "created_world_minute"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_combat_action_encounter_time",
        table_name="combat_actions",
    )
    op.drop_table("combat_actions")
