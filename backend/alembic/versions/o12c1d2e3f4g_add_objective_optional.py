"""add objective optional

Revision ID: o12c1d2e3f4g
Revises: n12b1c2d3e4f
Create Date: 2026-08-21

Phase 12C — Optional Objectives: a QuestObjective may be marked optional.
Quest completion (app.game.quests.service.complete_objective) only
requires the non-optional objectives; optional ones are still trackable
and completable, just never block the quest from finishing. Existing rows
default to required (optional=False) — unchanged behavior.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o12c1d2e3f4g"
down_revision: Union[str, None] = "n12b1c2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quest_objectives",
        sa.Column("optional", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("quest_objectives", "optional")
