"""add regional threats

Revision ID: au15l1m2n3o4
Revises: at15g1h2i3j4
Create Date: 2026-08-21

Phase 15L — Regional Threats, Wildlife & Ecology. New `regional_threats`
table: one population/habitat abstraction row per subregion (never
individual creature instances). No changes needed to any existing table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "au15l1m2n3o4"
down_revision: Union[str, None] = "at15g1h2i3j4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "regional_threats",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("subregion_id", sa.String(), sa.ForeignKey("subregions.id"), nullable=False),
        sa.Column("threat_type", sa.String(), nullable=False, server_default="WOLVES"),
        sa.Column("intensity", sa.String(), nullable=False, server_default="LOW"),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("regional_threats")
