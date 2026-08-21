"""add organization formality

Revision ID: x13e1f2g3h4i
Revises: w13d1e2f3g4h
Create Date: 2026-08-21

Phase 13E — Transported-Created Organizations: an organization may exist
informally before (or without ever) being legally recognized — existence
itself never requires formal registration, so INFORMAL is the default.
founding_group_id optionally links an organization back to the Group
(Phase 13A/13B) it grew out of, when it was founded that way.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x13e1f2g3h4i"
down_revision: Union[str, None] = "w13d1e2f3g4h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("formality", sa.String(), nullable=False, server_default="INFORMAL"),
    )
    op.add_column(
        "organizations",
        sa.Column("founding_group_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "founding_group_id")
    op.drop_column("organizations", "formality")
