"""add schedules to jobs and quests

Revision ID: v14b1c2d3e4f5
Revises: u14a1b2c3d4e5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "v14b1c2d3e4f5"
down_revision: str | None = "u14a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("shift_start_hour", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("shift_end_hour", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("schedule_on_notice", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("quests") as batch_op:
        batch_op.add_column(sa.Column("schedule_text", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("schedule_on_notice", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("quests") as batch_op:
        batch_op.drop_column("schedule_on_notice")
        batch_op.drop_column("schedule_text")
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("schedule_on_notice")
        batch_op.drop_column("shift_end_hour")
        batch_op.drop_column("shift_start_hour")
