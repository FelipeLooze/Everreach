"""add world generation seed metadata

Revision ID: ao15a1b2c3d4
Revises: an14k1l2m3n4
Create Date: 2026-08-21

Phase 15A — Campaign World Seed & Generation Metadata. Campaign gets a
root world_seed; Region gets a generation_seed derived from it (never
independently random — see app.game.world.generation.derive_seed) and a
generation_version recording which generator logic produced it, so a
future generator rewrite never silently regenerates already-persisted
worlds. Both new columns are nullable: existing saves predate this
concept and simply have no recorded seed (seed_initial_region self-heals
campaign.world_seed the next time it runs for an old save).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ao15a1b2c3d4"
down_revision: Union[str, None] = "an14k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.add_column(sa.Column("world_seed", sa.Integer(), nullable=True))

    with op.batch_alter_table("regions") as batch_op:
        batch_op.add_column(sa.Column("generation_seed", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("generation_version", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("regions") as batch_op:
        batch_op.drop_column("generation_version")
        batch_op.drop_column("generation_seed")

    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_column("world_seed")
