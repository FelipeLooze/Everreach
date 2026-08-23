"""add visual asset refs

Revision ID: e3c4d5e6f7g8
Revises: d2b3c4d5e6f7
Create Date: 2026-08-22

Phase 21Q — Future Generated-Asset Compatibility. Adds one generic,
opaque asset-reference slot to the same shared VisualIdentity table
every entity kind already uses for stable/current visual data — never
a ComfyUI-specific column, never an image-generation prompt.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3c4d5e6f7g8"
down_revision: Union[str, None] = "d2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "visual_identities",
        sa.Column("asset_refs_json", sa.String(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("visual_identities", "asset_refs_json")
