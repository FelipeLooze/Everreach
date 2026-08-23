"""add visual assets

Revision ID: g5e6f7g8h9i0
Revises: f4d5e6f7g8h9
Create Date: 2026-08-23

Phase 23D-E — VisualAsset: a successfully materialized generated
visual asset, distinct from the VisualGenerationRequest attempt that
produced it. See app.db.models.visual_asset.VisualAsset.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g5e6f7g8h9i0"
down_revision: Union[str, None] = "f4d5e6f7g8h9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visual_assets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=True),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("workflow_key", sa.String(), nullable=False),
        sa.Column("workflow_version", sa.String(), nullable=False),
        sa.Column("model_identifier", sa.String(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("validation_status", sa.String(), nullable=False, server_default="UNREVIEWED"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_canonical_reference", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_visual_asset_current",
        "visual_assets",
        ["campaign_id", "entity_type", "entity_id", "asset_type", "is_current"],
    )


def downgrade() -> None:
    op.drop_index("ix_visual_asset_current", table_name="visual_assets")
    op.drop_table("visual_assets")
