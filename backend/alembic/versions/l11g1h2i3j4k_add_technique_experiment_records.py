"""add technique experiment records

Revision ID: l11g1h2i3j4k
Revises: k11f1g2h3i4j
Create Date: 2026-08-21

Phase 11I — Player-Created / Emergent Techniques: an idempotent record of
one freeform attempt at a not-yet-recognized maneuver, mirroring
TechniqueUseRecord's shape for an already-learned technique's use.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l11g1h2i3j4k"
down_revision: Union[str, None] = "k11f1g2h3i4j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "technique_experiment_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("pattern_key", sa.String(), nullable=False),
        sa.Column("domain_keys", sa.String(), nullable=False),
        sa.Column("technique_type", sa.String(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("roll", sa.Integer(), nullable=False),
        sa.Column("modifier", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("dc", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("resource_key", sa.String(), nullable=False),
        sa.Column("resource_cost", sa.Float(), nullable=False),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "character_id",
            "action_key",
            name="uq_technique_experiment_action",
        ),
    )


def downgrade() -> None:
    op.drop_table("technique_experiment_records")
