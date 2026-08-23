"""add visual generation request attempt count

Revision ID: h6f7g8h9i0j1
Revises: g5e6f7g8h9i0
Create Date: 2026-08-23

Phase 23D-J — Status & Failure Handling. attempt_count lets
app.game.visual.retry_policy enforce a bounded retry policy across a
chain of VisualGenerationRequest rows for the same generation attempt.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h6f7g8h9i0j1"
down_revision: Union[str, None] = "g5e6f7g8h9i0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "visual_generation_requests",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("visual_generation_requests", "attempt_count")
