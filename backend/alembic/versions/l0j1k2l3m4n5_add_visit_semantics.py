"""add visit-based location semantics

Revision ID: l0j1k2l3m4n5
Revises: k9i0j1k2l3m4
Create Date: 2026-08-28

All changes are additive. Existing discovery statuses and world-level fields
remain readable during the transition.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l0j1k2l3m4n5"
down_revision: Union[str, None] = "k9i0j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("locations") as batch:
        batch.add_column(sa.Column("identity_hidden", sa.Boolean(), server_default=sa.text("0"), nullable=False))
        batch.add_column(sa.Column("unrevealed_name", sa.String(), nullable=True))
    with op.batch_alter_table("character_location_discoveries") as batch:
        batch.add_column(sa.Column("last_visited_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("visit_count", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("character_location_discoveries") as batch:
        batch.drop_column("visit_count")
        batch.drop_column("last_visited_at")
    with op.batch_alter_table("locations") as batch:
        batch.drop_column("unrevealed_name")
        batch.drop_column("identity_hidden")
