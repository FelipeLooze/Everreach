"""add visual generation requests

Revision ID: f4d5e6f7g8h9
Revises: e3c4d5e6f7g8
Create Date: 2026-08-23

Phase 23D-D — Visual Generation Request. Records ATTEMPTS to
materialize a visual asset through ComfyUI; see
app.db.models.visual_generation_request.VisualGenerationRequest.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4d5e6f7g8h9"
down_revision: Union[str, None] = "e3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visual_generation_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=True),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("workflow_key", sa.String(), nullable=False),
        sa.Column("workflow_version", sa.String(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("result_asset_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_visual_generation_request_dedup",
        "visual_generation_requests",
        ["campaign_id", "entity_type", "entity_id", "asset_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_visual_generation_request_dedup", table_name="visual_generation_requests")
    op.drop_table("visual_generation_requests")
