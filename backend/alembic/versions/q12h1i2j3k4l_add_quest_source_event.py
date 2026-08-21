"""add quest source event

Revision ID: q12h1i2j3k4l
Revises: p12d1e2f3g4h
Create Date: 2026-08-21

Phase 12H — Emergent World Quests: a Quest may optionally reference the
WorldEvent that justified its creation (source_event_id). WORLD FIRST,
QUEST SECOND — the event already happened; this is just the backward
link, and doubles as the natural idempotency key (at most one Quest per
triggering event, see app.game.quests.emergence).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q12h1i2j3k4l"
down_revision: Union[str, None] = "p12d1e2f3g4h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quests", sa.Column("source_event_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("quests", "source_event_id")
