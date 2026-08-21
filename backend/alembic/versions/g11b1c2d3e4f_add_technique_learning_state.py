"""add technique learning state

Revision ID: g11b1c2d3e4f
Revises: f11a1b2c3d4e
Create Date: 2026-08-21

Phase 11B — Technique Discovery & Learning: a character's relationship with
a technique now tracks how far along they are (AWARE/LEARNING/LEARNED) and
how they got there (origin), instead of a bare has-it/doesn't-have-it link.
Existing rows default to LEARNED/SELF_DISCOVERED, preserving the old
ungated-grant behavior for anything already granted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g11b1c2d3e4f"
down_revision: Union[str, None] = "f11a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "character_techniques",
        sa.Column("learning_state", sa.String(), nullable=False, server_default="LEARNED"),
    )
    op.add_column(
        "character_techniques",
        sa.Column("origin", sa.String(), nullable=False, server_default="SELF_DISCOVERED"),
    )
    op.add_column(
        "character_techniques",
        sa.Column("world_minute", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("character_techniques", "world_minute")
    op.drop_column("character_techniques", "origin")
    op.drop_column("character_techniques", "learning_state")
