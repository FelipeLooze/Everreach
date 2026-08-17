"""remove regional boss fields

Revision ID: f9667339ebe0
Revises: 4b7a31d9e620
Create Date: 2026-08-17 14:26:45.542851

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f9667339ebe0'
down_revision: Union[str, None] = '4b7a31d9e620'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("regions") as batch_op:
        batch_op.drop_column("main_boss_requirements")
        batch_op.drop_column("main_boss_name")
        batch_op.drop_column("main_boss_defeated")
        batch_op.drop_column("main_boss_location")


def downgrade() -> None:
    with op.batch_alter_table("regions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "main_boss_location",
                sa.String(),
                nullable=False,
                server_default="UNKNOWN",
            )
        )
        batch_op.add_column(
            sa.Column(
                "main_boss_defeated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "main_boss_name",
                sa.String(),
                nullable=False,
                server_default="UNKNOWN",
            )
        )
        batch_op.add_column(
            sa.Column(
                "main_boss_requirements",
                sa.String(),
                nullable=False,
                server_default="UNKNOWN",
            )
        )
