"""add background profession affinity

Revision ID: f8c1d2e3a4b5
Revises: e8b1c2d3f4a5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f8c1d2e3a4b5"
down_revision: Union[str, None] = "e8b1c2d3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("characters") as batch_op:
        batch_op.add_column(sa.Column("background", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("profession_affinity_key", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_character_profession_affinity",
            "professions",
            ["profession_affinity_key"],
            ["key"],
        )

    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.add_column(
            sa.Column("profession_affinity_key", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_simulated_player_profession_affinity",
            "professions",
            ["profession_affinity_key"],
            ["key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("simulated_players") as batch_op:
        batch_op.drop_constraint(
            "fk_simulated_player_profession_affinity",
            type_="foreignkey",
        )
        batch_op.drop_column("profession_affinity_key")

    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_constraint(
            "fk_character_profession_affinity",
            type_="foreignkey",
        )
        batch_op.drop_column("profession_affinity_key")
        batch_op.drop_column("background")
