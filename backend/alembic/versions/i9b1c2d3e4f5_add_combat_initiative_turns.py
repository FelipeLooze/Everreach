"""add combat initiative and turns

Revision ID: i9b1c2d3e4f5
Revises: h9a1b2c3d4e5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "i9b1c2d3e4f5"
down_revision: Union[str, None] = "h9a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("combat_encounters") as batch_op:
        batch_op.add_column(sa.Column("current_turn_order", sa.Integer(), nullable=True))
    with op.batch_alter_table("combat_participants") as batch_op:
        batch_op.add_column(sa.Column("initiative_roll", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("initiative_modifier", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("initiative_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("turn_order", sa.Integer(), nullable=True))

    op.create_table(
        "combat_turns",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("turn_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_world_minute", sa.Integer(), nullable=False),
        sa.Column("ended_world_minute", sa.Integer(), nullable=True),
        sa.Column("completion_key", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["encounter_id"], ["combat_encounters.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["combat_participants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "encounter_id",
            "completion_key",
            name="uq_combat_turn_completion_key",
        ),
        sa.UniqueConstraint(
            "encounter_id",
            "round_number",
            "turn_order",
            name="uq_combat_turn_slot",
        ),
    )
    op.create_index(
        "ix_combat_turn_encounter_status",
        "combat_turns",
        ["encounter_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_combat_turn_encounter_status", table_name="combat_turns")
    op.drop_table("combat_turns")
    with op.batch_alter_table("combat_participants") as batch_op:
        batch_op.drop_column("turn_order")
        batch_op.drop_column("initiative_score")
        batch_op.drop_column("initiative_modifier")
        batch_op.drop_column("initiative_roll")
    with op.batch_alter_table("combat_encounters") as batch_op:
        batch_op.drop_column("current_turn_order")
