"""add profession foundation

Revision ID: e8b1c2d3f4a5
Revises: d7b5a1f3c902
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e8b1c2d3f4a5"
down_revision: Union[str, None] = "d7b5a1f3c902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "professions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "character_professions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("profession_id", sa.String(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("xp", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["profession_id"], ["professions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "profession_id",
            name="uq_character_profession",
        ),
    )


def downgrade() -> None:
    op.drop_table("character_professions")
    op.drop_table("professions")
