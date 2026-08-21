"""add objective type and trigger

Revision ID: n12b1c2d3e4f
Revises: m12a1b2c3d4e
Create Date: 2026-08-21

Phase 12B — Objectives: a QuestObjective now carries a display category
(objective_type) and a structured, backend-authoritative completion
trigger (trigger_type + optional trigger_subject_id) evaluated by
app.game.quests.service.evaluate_objective_trigger, replacing free-text
substring matching. Existing rows default to INVESTIGATION/MANUAL (no
automatic completion — matches their prior text-matched-only behavior).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n12b1c2d3e4f"
down_revision: Union[str, None] = "m12a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quest_objectives",
        sa.Column("objective_type", sa.String(), nullable=False, server_default="INVESTIGATION"),
    )
    op.add_column(
        "quest_objectives",
        sa.Column("trigger_type", sa.String(), nullable=False, server_default="MANUAL"),
    )
    op.add_column(
        "quest_objectives",
        sa.Column("trigger_subject_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quest_objectives", "trigger_subject_id")
    op.drop_column("quest_objectives", "trigger_type")
    op.drop_column("quest_objectives", "objective_type")
