"""add authoritative character recovery

Revision ID: p9i1j2k3l4m5
Revises: o9h1i2j3k4l5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p9i1j2k3l4m5"
down_revision: Union[str, None] = "o9h1i2j3k4l5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_recoveries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("recovery_key", sa.String(), nullable=False),
        sa.Column("recovery_type", sa.String(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("started_world_minute", sa.Integer(), nullable=False),
        sa.Column("hp_before", sa.Float(), nullable=False),
        sa.Column("hp_after", sa.Float(), nullable=False),
        sa.Column("mana_before", sa.Float(), nullable=False),
        sa.Column("mana_after", sa.Float(), nullable=False),
        sa.Column("stamina_before", sa.Float(), nullable=False),
        sa.Column("stamina_after", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "recovery_key",
            name="uq_character_recovery_key",
        ),
    )
    op.create_index(
        "ix_character_recovery_campaign_time",
        "character_recoveries",
        ["campaign_id", "started_world_minute"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_character_recovery_campaign_time",
        table_name="character_recoveries",
    )
    op.drop_table("character_recoveries")
