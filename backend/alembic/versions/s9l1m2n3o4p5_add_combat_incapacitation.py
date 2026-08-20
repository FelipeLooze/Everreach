"""add combat incapacitation and critical checks

Revision ID: s9l1m2n3o4p5
Revises: r9k1l2m3n4o5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s9l1m2n3o4p5"
down_revision: Union[str, None] = "r9k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.add_column(sa.Column("incapacitated", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.add_column(sa.Column("incapacitating", sa.Boolean(), nullable=True))
    op.create_table(
        "combat_incapacitations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("source_action_id", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stabilization_successes", sa.Integer(), nullable=False),
        sa.Column("death_failures", sa.Integer(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.Column("resolved_world_minute", sa.Integer(), nullable=True),
        sa.Column("resolution_reason", sa.String(), nullable=False),
        sa.Column("recovery_key", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["encounter_id"], ["combat_encounters.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["combat_participants.id"]),
        sa.ForeignKeyConstraint(["source_action_id"], ["combat_actions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("encounter_id", "participant_id", name="uq_combat_incapacitation_participant"),
        sa.UniqueConstraint("source_action_id", name="uq_combat_incapacitation_source_action"),
    )
    op.create_index("ix_combat_incapacitation_actor_status", "combat_incapacitations", ["actor_type", "actor_id", "status"])
    op.create_table(
        "combat_critical_checks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("incapacitation_id", sa.String(), nullable=False),
        sa.Column("check_key", sa.String(), nullable=False),
        sa.Column("roll", sa.Integer(), nullable=False),
        sa.Column("modifier", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("dc", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("successes_before", sa.Integer(), nullable=False),
        sa.Column("successes_after", sa.Integer(), nullable=False),
        sa.Column("failures_before", sa.Integer(), nullable=False),
        sa.Column("failures_after", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["incapacitation_id"], ["combat_incapacitations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incapacitation_id", "check_key", name="uq_combat_critical_check_key"),
    )


def downgrade() -> None:
    op.drop_table("combat_critical_checks")
    op.drop_index("ix_combat_incapacitation_actor_status", table_name="combat_incapacitations")
    op.drop_table("combat_incapacitations")
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_column("incapacitating")
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.drop_column("incapacitated")
