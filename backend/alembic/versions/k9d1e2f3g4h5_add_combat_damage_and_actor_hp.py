"""add combat damage and actor hp

Revision ID: k9d1e2f3g4h5
Revises: j9c1d2e3f4g5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k9d1e2f3g4h5"
down_revision: Union[str, None] = "j9c1d2e3f4g5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "hp_current",
                sa.Float(),
                nullable=False,
                server_default="10",
            )
        )
        batch_op.add_column(
            sa.Column("hp_max", sa.Float(), nullable=False, server_default="10")
        )
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.add_column(
            sa.Column(
                "hp_current",
                sa.Float(),
                nullable=False,
                server_default="20",
            )
        )
        batch_op.add_column(
            sa.Column("hp_max", sa.Float(), nullable=False, server_default="20")
        )
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.add_column(sa.Column("damage_roll", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("damage_dice", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("damage_modifier", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("damage_total", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("target_hp_before", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("target_hp_after", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("lethal", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_column("lethal")
        batch_op.drop_column("target_hp_after")
        batch_op.drop_column("target_hp_before")
        batch_op.drop_column("damage_total")
        batch_op.drop_column("damage_modifier")
        batch_op.drop_column("damage_dice")
        batch_op.drop_column("damage_roll")
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.drop_column("hp_max")
        batch_op.drop_column("hp_current")
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.drop_column("hp_max")
        batch_op.drop_column("hp_current")
