"""add structured simulated player goals

Revision ID: 9eabe3fb45ce
Revises: aab09fe9f20f
Create Date: 2026-08-19 00:37:03.148485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9eabe3fb45ce'
down_revision: Union[str, None] = 'aab09fe9f20f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulated_players",
        sa.Column(
            "goal_type",
            sa.String(),
            nullable=False,
            server_default="NONE",
        ),
    )

    op.add_column(
        "simulated_players",
        sa.Column(
            "goal_subject",
            sa.String(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "simulated_players",
        "goal_subject",
    )
    op.drop_column(
        "simulated_players",
        "goal_type",
    )