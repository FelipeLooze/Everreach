"""add technique pattern evidence

Revision ID: h11c1d2e3f4g
Revises: g11b1c2d3e4f
Create Date: 2026-08-21

Phase 11C — Technique Evidence & Training: tracks reproducibility of a
specific attempted maneuver ("pattern_key") before any Technique exists for
it, mirroring the domain evidence tables from Phase 8.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h11c1d2e3f4g"
down_revision: Union[str, None] = "g11b1c2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_technique_pattern_evidence",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("pattern_key", sa.String(), nullable=False),
        sa.Column("domain_keys", sa.String(), nullable=False),
        sa.Column("technique_type", sa.String(), nullable=False),
        sa.Column("depth", sa.Float(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "pattern_key",
            name="uq_character_technique_pattern_evidence",
        ),
    )
    op.create_table(
        "technique_pattern_evidence_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("pattern_key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("evidence_key", sa.String(), nullable=False),
        sa.Column("context_key", sa.String(), nullable=False),
        sa.Column("base_amount", sa.Float(), nullable=False),
        sa.Column("awarded_amount", sa.Float(), nullable=False),
        sa.Column("repetition_count", sa.Integer(), nullable=False),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_technique_pattern_evidence_character_pattern_time",
        "technique_pattern_evidence_records",
        ["character_id", "pattern_key", "world_minute"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_technique_pattern_evidence_character_pattern_time",
        table_name="technique_pattern_evidence_records",
    )
    op.drop_table("technique_pattern_evidence_records")
    op.drop_table("character_technique_pattern_evidence")
