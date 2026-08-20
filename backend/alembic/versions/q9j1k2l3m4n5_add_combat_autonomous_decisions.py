"""add combat autonomous decisions

Revision ID: q9j1k2l3m4n5
Revises: p9i1j2k3l4m5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "q9j1k2l3m4n5"
down_revision: Union[str, None] = "p9i1j2k3l4m5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "combat_autonomous_decisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("actor_participant_id", sa.String(), nullable=False),
        sa.Column("target_participant_id", sa.String(), nullable=True),
        sa.Column("combat_action_id", sa.String(), nullable=True),
        sa.Column("tactical_action_id", sa.String(), nullable=True),
        sa.Column("decision_key", sa.String(), nullable=False),
        sa.Column("decision_kind", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("risk_tolerance", sa.String(), nullable=False),
        sa.Column("hp_ratio", sa.Float(), nullable=False),
        sa.Column("stamina_ratio", sa.Float(), nullable=False),
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
        sa.ForeignKeyConstraint(["combat_action_id"], ["combat_actions.id"]),
        sa.ForeignKeyConstraint(
            ["tactical_action_id"],
            ["combat_tactical_actions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "encounter_id",
            "decision_key",
            name="uq_combat_autonomous_decision_key",
        ),
        sa.UniqueConstraint(
            "turn_id",
            name="uq_combat_autonomous_decision_turn",
        ),
    )
    op.create_index(
        "ix_combat_autonomous_decision_encounter_time",
        "combat_autonomous_decisions",
        ["encounter_id", "created_world_minute"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_combat_autonomous_decision_encounter_time",
        table_name="combat_autonomous_decisions",
    )
    op.drop_table("combat_autonomous_decisions")
