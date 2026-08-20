"""add combat conditions

Revision ID: m9f1g2h3i4j5
Revises: l9e1f2g3h4i5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "m9f1g2h3i4j5"
down_revision: Union[str, None] = "l9e1f2g3h4i5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "combat_conditions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("source_action_id", sa.String(), nullable=True),
        sa.Column("application_key", sa.String(), nullable=False),
        sa.Column("condition_type", sa.String(), nullable=False),
        sa.Column("remaining_turns", sa.Integer(), nullable=False),
        sa.Column("applied_round", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("removed_round", sa.Integer(), nullable=True),
        sa.Column("removal_reason", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["combat_encounters.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["combat_participants.id"]),
        sa.ForeignKeyConstraint(["source_action_id"], ["combat_actions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "encounter_id",
            "application_key",
            name="uq_combat_condition_application",
        ),
    )
    op.create_index(
        "ix_combat_condition_participant_active",
        "combat_conditions",
        ["participant_id", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_combat_condition_participant_active",
        table_name="combat_conditions",
    )
    op.drop_table("combat_conditions")
