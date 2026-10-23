"""add measurable shared goals to organizations

Revision ID: t13b1c2d3e4f5
Revises: s13a1b2c3d4e5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t13b1c2d3e4f5"
down_revision: str | None = "s13a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("organization_goals") as batch_op:
        batch_op.add_column(sa.Column("metric", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("target", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("organization_goals") as batch_op:
        batch_op.drop_column("progress")
        batch_op.drop_column("target")
        batch_op.drop_column("metric")
