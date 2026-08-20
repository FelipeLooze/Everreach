"""add combat resource costs

Revision ID: l9e1f2g3h4i5
Revises: k9d1e2f3g4h5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "l9e1f2g3h4i5"
down_revision: Union[str, None] = "k9d1e2f3g4h5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.add_column(
            sa.Column("mana_current", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("mana_max", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "stamina_current",
                sa.Float(),
                nullable=False,
                server_default="10",
            )
        )
        batch_op.add_column(
            sa.Column(
                "stamina_max",
                sa.Float(),
                nullable=False,
                server_default="10",
            )
        )
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.add_column(
            sa.Column(
                "mana_current",
                sa.Float(),
                nullable=False,
                server_default="10",
            )
        )
        batch_op.add_column(
            sa.Column("mana_max", sa.Float(), nullable=False, server_default="10")
        )
        batch_op.add_column(
            sa.Column(
                "stamina_current",
                sa.Float(),
                nullable=False,
                server_default="20",
            )
        )
        batch_op.add_column(
            sa.Column(
                "stamina_max",
                sa.Float(),
                nullable=False,
                server_default="20",
            )
        )
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.add_column(sa.Column("resource_key", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("resource_cost", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("resource_before", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("resource_after", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_column("resource_after")
        batch_op.drop_column("resource_before")
        batch_op.drop_column("resource_cost")
        batch_op.drop_column("resource_key")
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.drop_column("stamina_max")
        batch_op.drop_column("stamina_current")
        batch_op.drop_column("mana_max")
        batch_op.drop_column("mana_current")
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.drop_column("stamina_max")
        batch_op.drop_column("stamina_current")
        batch_op.drop_column("mana_max")
        batch_op.drop_column("mana_current")
