"""add subregion identity

Revision ID: ar15d1e2f3g4
Revises: aq15c1d2e3f4
Create Date: 2026-08-21

Phase 15D — Subregions & Regional Identity. Subregion gains biome,
danger_level, population_density, culture_summary, economy_summary —
deliberately not interchangeable per subregion (spec). The anchor
subregion (containing the fixed starting village) is generated
constrained to stay playable (plains, SAFE/LOW danger); every other
subregion rolls freely from app.game.world.generator.generate_subregion_identity.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ar15d1e2f3g4"
down_revision: Union[str, None] = "aq15c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("subregions") as batch_op:
        batch_op.add_column(
            sa.Column("biome", sa.String(), nullable=False, server_default="PLAINS")
        )
        batch_op.add_column(
            sa.Column("danger_level", sa.String(), nullable=False, server_default="LOW")
        )
        batch_op.add_column(
            sa.Column("population_density", sa.String(), nullable=False, server_default="MODERATE")
        )
        batch_op.add_column(
            sa.Column("culture_summary", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("economy_summary", sa.String(), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("subregions") as batch_op:
        batch_op.drop_column("economy_summary")
        batch_op.drop_column("culture_summary")
        batch_op.drop_column("population_density")
        batch_op.drop_column("danger_level")
        batch_op.drop_column("biome")
