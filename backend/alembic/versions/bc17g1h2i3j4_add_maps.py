"""add maps

Revision ID: bc17g1h2i3j4
Revises: bb17c1d2e3f4
Create Date: 2026-08-22

Phase 17G — Physical Maps. New `maps` table: a thin overlay on a real
Phase 10 ItemInstance (ItemType.MAP, always instance_mode=UNIQUE),
holding a frozen JSON snapshot of the creator's geographic knowledge at
creation time. No changes to any existing table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "bc17g1h2i3j4"
down_revision: Union[str, None] = "bb17c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "maps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("item_instance_id", sa.String(), sa.ForeignKey("item_instances.id"), nullable=False, unique=True),
        sa.Column("subject_kind", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("creator_type", sa.String(), nullable=False),
        sa.Column("creator_id", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("content_json", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("maps")
