"""add system progression context

Revision ID: f8j1a2b3c4d5
Revises: e8i1f2a3b4c5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f8j1a2b3c4d5"
down_revision: Union[str, None] = "e8i1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE attribute_definitions "
        "SET description = 'Atributo exclusivo do protagonista reservado "
        "para futuras resoluções autoritativas de loot.' "
        "WHERE key = 'LUCK'"
    )
    op.create_table(
        "applied_progression_outcomes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("outcome_key", sa.String(), nullable=False),
        sa.Column("applied_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "character_id",
            "outcome_key",
            name="uq_applied_progression_outcome",
        ),
    )


def downgrade() -> None:
    op.drop_table("applied_progression_outcomes")
