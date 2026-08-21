"""add organization origin

Revision ID: w13d1e2f3g4h
Revises: v13c1d2e3f4g
Create Date: 2026-08-21

Phase 13D — Native Organizations: an Organization now declares whether it
predated transported people (NATIVE) or was founded by them
(TRANSPORTED_CREATED, Phase 13E), plus an optional per-organization
disposition toward transported people — deliberately not a single
hardcoded universal attitude.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w13d1e2f3g4h"
down_revision: Union[str, None] = "v13c1d2e3f4g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("origin", sa.String(), nullable=False, server_default="NATIVE"),
    )
    op.add_column(
        "organizations",
        sa.Column("transported_people_stance", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "transported_people_stance")
    op.drop_column("organizations", "origin")
