"""add quest deadlines

Revision ID: p12d1e2f3g4h
Revises: o12c1d2e3f4g
Create Date: 2026-08-21

Phase 12D — Failure: a Quest may carry a world-minute deadline for the
opportunity itself (e.g. "the caravan leaves in two days" — nobody's
participation required, it just closes), and a CharacterQuest may
separately carry a deadline for one character's active participation
(e.g. urgency that starts once accepted). Both are nullable — most quests
have no deadline at all. See app.game.quests.service.check_deadlines.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p12d1e2f3g4h"
down_revision: Union[str, None] = "o12c1d2e3f4g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quests", sa.Column("deadline_world_minute", sa.Integer(), nullable=True))
    op.add_column("character_quests", sa.Column("deadline_world_minute", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("character_quests", "deadline_world_minute")
    op.drop_column("quests", "deadline_world_minute")
