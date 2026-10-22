"""add organization focus for transported-founded guilds

Revision ID: s13a1b2c3d4e5
Revises: r12m1n2o3p4q
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s13a1b2c3d4e5"
down_revision: str | None = "r12m1n2o3p4q"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(sa.Column("focus", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_column("focus")
