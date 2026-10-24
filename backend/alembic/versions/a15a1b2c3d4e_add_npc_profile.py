"""add npc age and personality profile

Starting village population, part 1 (2026-10-24): every NPC gets an age and
a structured profile (temperament, speech, stance toward transported people,
want, worry, secret) instead of a one-line personality.

Revision ID: a15a1b2c3d4e
Revises: x14d1e2f3a4b5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a15a1b2c3d4e"
down_revision: str | None = "x14d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.add_column(sa.Column("age", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("profile_json", sa.String(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.drop_column("profile_json")
        batch_op.drop_column("age")
