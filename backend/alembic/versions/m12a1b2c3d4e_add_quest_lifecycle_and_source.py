"""add quest lifecycle and source

Revision ID: m12a1b2c3d4e
Revises: l11g1h2i3j4k
Create Date: 2026-08-21

Phase 12A — Quest Lifecycle: a Quest now carries its own world-level
status (AVAILABLE by default; EXPIRED/CANCELLED/RESOLVED_EXTERNALLY once
the situation moves on independent of any one character — see
app.game.quests.service) and a source describing where it originated.
Existing rows default to AVAILABLE/SELF_DISCOVERED.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m12a1b2c3d4e"
down_revision: Union[str, None] = "l11g1h2i3j4k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quests",
        sa.Column("status", sa.String(), nullable=False, server_default="AVAILABLE"),
    )
    op.add_column(
        "quests",
        sa.Column("source", sa.String(), nullable=False, server_default="SELF_DISCOVERED"),
    )


def downgrade() -> None:
    op.drop_column("quests", "source")
    op.drop_column("quests", "status")
