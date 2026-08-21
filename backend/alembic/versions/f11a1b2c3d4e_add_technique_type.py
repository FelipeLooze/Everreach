"""add technique type

Revision ID: f11a1b2c3d4e
Revises: e10l1m2n3o4p
Create Date: 2026-08-21

Phase 11A — Technique Foundation: a Technique now declares what powers its
execution (PHYSICAL/MAGICAL/HYBRID). Existing rows default to PHYSICAL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f11a1b2c3d4e"
down_revision: Union[str, None] = "e10l1m2n3o4p"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "techniques",
        sa.Column("technique_type", sa.String(), nullable=False, server_default="PHYSICAL"),
    )


def downgrade() -> None:
    op.drop_column("techniques", "technique_type")
