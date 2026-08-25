"""add npc workplace location

Revision ID: j8h9i0j1k2l3
Revises: i7g8h9i0j1k2
Create Date: 2026-08-25

Simplification Pass S1.2 — additive, nullable. An NPC's existing
location_id stays its home/base location, unchanged; this is the
separate, optional service location (inn/forge/etc.) it is normally
found at while WORKING. NULL for every existing NPC in every existing
save — no backfill, no behavior change for old saves until/unless a
future write explicitly sets it (world generation now does, for the
starting village's blacksmith and innkeeper — see app.game.world.seed).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j8h9i0j1k2l3"
down_revision: Union[str, None] = "i7g8h9i0j1k2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.add_column(
            sa.Column("workplace_location_id", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_npcs_workplace_location_id",
            "locations",
            ["workplace_location_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("npcs") as batch_op:
        batch_op.drop_constraint(
            "fk_npcs_workplace_location_id",
            type_="foreignkey",
        )
        batch_op.drop_column("workplace_location_id")
