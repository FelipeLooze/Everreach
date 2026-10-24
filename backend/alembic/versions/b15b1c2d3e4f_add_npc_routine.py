"""add npc daily routine and the building being visited

Starting village population, part 2 (2026-10-24): residents follow an
hour-by-hour routine (app.game.npcs.residents) and may be visiting a
building (the inn at lunch) instead of their base location.

Revision ID: b15b1c2d3e4f
Revises: a15a1b2c3d4e
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b15b1c2d3e4f"
down_revision: str | None = "a15a1b2c3d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.add_column(sa.Column("routine_json", sa.String(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("visiting_location_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_npcs_visiting_location_id_locations", "locations", ["visiting_location_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.drop_constraint("fk_npcs_visiting_location_id_locations", type_="foreignkey")
        batch_op.drop_column("visiting_location_id")
        batch_op.drop_column("routine_json")
