"""add combat tactical actions

Revision ID: o9h1i2j3k4l5
Revises: n9g1h2i3j4k5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "o9h1i2j3k4l5"
down_revision: Union[str, None] = "n9g1h2i3j4k5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "combat_tactical_actions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("actor_participant_id", sa.String(), nullable=False),
        sa.Column("target_participant_id", sa.String(), nullable=True),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("resource_key", sa.String(), nullable=True),
        sa.Column("resource_cost", sa.Float(), nullable=True),
        sa.Column("resource_before", sa.Float(), nullable=True),
        sa.Column("resource_after", sa.Float(), nullable=True),
        sa.Column("previous_range_band", sa.String(), nullable=True),
        sa.Column("new_range_band", sa.String(), nullable=True),
        sa.Column("roll", sa.Integer(), nullable=True),
        sa.Column("modifier", sa.Integer(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("dc", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
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
            name="uq_combat_tactical_action_key",
        ),
        sa.UniqueConstraint("turn_id", name="uq_combat_tactical_action_turn"),
    )
    op.create_index(
        "ix_combat_tactical_action_encounter_time",
        "combat_tactical_actions",
        ["encounter_id", "created_world_minute"],
    )
    with op.batch_alter_table("combat_conditions") as batch_op:
        batch_op.add_column(
            sa.Column("source_tactical_action_id", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_combat_condition_tactical_action",
            "combat_tactical_actions",
            ["source_tactical_action_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("combat_conditions") as batch_op:
        batch_op.drop_constraint(
            "fk_combat_condition_tactical_action",
            type_="foreignkey",
        )
        batch_op.drop_column("source_tactical_action_id")
    op.drop_index(
        "ix_combat_tactical_action_encounter_time",
        table_name="combat_tactical_actions",
    )
    op.drop_table("combat_tactical_actions")
