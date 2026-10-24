"""mark an NPC as a creature of a species

Hunting around the starting village (2026-10-24): wolves, boars, deer… are
NPC rows the combat engine already fights, marked with their species so
they never pass for people (no names, talk, routines or knowledge).

Revision ID: e15e1f2a3b4c
Revises: d15d1e2f3a4b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e15e1f2a3b4c"
down_revision: str | None = "d15d1e2f3a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.add_column(sa.Column("creature_species", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.drop_column("creature_species")
