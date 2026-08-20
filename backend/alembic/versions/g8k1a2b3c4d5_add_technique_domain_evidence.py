"""add authoritative technique domain evidence

Revision ID: g8k1a2b3c4d5
Revises: f8j1a2b3c4d5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "g8k1a2b3c4d5"
down_revision: Union[str, None] = "f8j1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "technique_domains",
        sa.Column("technique_id", sa.String(), nullable=False),
        sa.Column("domain_key", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["domain_key"], ["domain_definitions.key"]),
        sa.ForeignKeyConstraint(["technique_id"], ["techniques.id"]),
        sa.PrimaryKeyConstraint("technique_id", "domain_key"),
    )
    op.create_table(
        "technique_use_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("technique_id", sa.String(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("roll", sa.Integer(), nullable=False),
        sa.Column("modifier", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("dc", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["technique_id"], ["techniques.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "character_id",
            "action_key",
            name="uq_technique_use_action",
        ),
    )
    op.create_index(
        "ix_technique_use_character_time",
        "technique_use_records",
        ["character_id", "world_minute"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_technique_use_character_time",
        table_name="technique_use_records",
    )
    op.drop_table("technique_use_records")
    op.drop_table("technique_domains")
