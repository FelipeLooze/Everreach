"""add notices

Revision ID: r12i1j2k3l4m
Revises: q12h1i2j3k4l
Create Date: 2026-08-21

Phase 12I — Quest / Notice Boards: a Notice is a real posting on a board.
The board itself is not a new concept — it's an existing LocationFeature
(Phase 4); a Notice just points at one via board_feature_id. Nothing
creates a Notice except an explicit call with real context (author,
quest link, category) — opening a board never generates one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r12i1j2k3l4m"
down_revision: Union[str, None] = "q12h1i2j3k4l"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("board_feature_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("author_npc_id", sa.String(), nullable=True),
        sa.Column("quest_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("posted_world_minute", sa.Integer(), nullable=False),
        sa.Column("expires_world_minute", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["board_feature_id"], ["location_features.id"]),
        sa.ForeignKeyConstraint(["author_npc_id"], ["npcs.id"]),
        sa.ForeignKeyConstraint(["quest_id"], ["quests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("notices")
