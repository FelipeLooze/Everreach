"""add visual asset spec fingerprint

Revision ID: i7g8h9i0j1k2
Revises: h6f7g8h9i0j1
Create Date: 2026-08-23

Phase 23D-K — Deduplication & Reuse. spec_fingerprint lets
app.game.visual.dedup.find_reusable_asset recognize an existing
VisualAsset already matches what a new request would generate.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i7g8h9i0j1k2"
down_revision: Union[str, None] = "h6f7g8h9i0j1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "visual_assets",
        sa.Column("spec_fingerprint", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("visual_assets", "spec_fingerprint")
