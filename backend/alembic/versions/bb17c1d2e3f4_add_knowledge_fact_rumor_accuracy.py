"""add knowledge fact rumor accuracy

Revision ID: bb17c1d2e3f4
Revises: ba17b1c2d3e4
Create Date: 2026-08-22

Phase 17C — Rumors & Geographic Information Sources. Adds a nullable
`rumor_accuracy` column to knowledge_facts: the backend's own private
truth about how a rumor's statement relates to Canon
(TRUE/FALSE/PARTIALLY_TRUE/OUTDATED/MISINTERPRETED), never exposed to
players. NULL for every non-rumor fact.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "bb17c1d2e3f4"
down_revision: Union[str, None] = "ba17b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_facts",
        sa.Column("rumor_accuracy", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_facts", "rumor_accuracy")
