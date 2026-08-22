"""add knowledge knower precision

Revision ID: ba17b1c2d3e4
Revises: az16e1f2g3h4
Create Date: 2026-08-22

Phase 17B — Geographic Information Precision. Adds a nullable
`precision` column to knowledge_knowers: how DETAILED a grant is
(VAGUE/APPROXIMATE/GOOD/PRECISE), independent of the existing
`certainty` column (how SURE the knower is). Only geographic grants
populate it; every other Knowledge grant leaves it NULL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ba17b1c2d3e4"
down_revision: Union[str, None] = "az16e1f2g3h4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_knowers",
        sa.Column("precision", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_knowers", "precision")
