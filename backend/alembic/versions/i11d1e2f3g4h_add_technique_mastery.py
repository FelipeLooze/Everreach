"""add technique mastery

Revision ID: i11d1e2f3g4h
Revises: h11c1d2e3f4g
Create Date: 2026-08-21

Phase 11D — Mastery: how reliably a LEARNED technique can be executed.
Continuous internally, exposed to the player only as a qualitative tier.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i11d1e2f3g4h"
down_revision: Union[str, None] = "h11c1d2e3f4g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "character_techniques",
        sa.Column("mastery", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("character_techniques", "mastery")
