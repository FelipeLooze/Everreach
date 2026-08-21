"""add organization actions

Revision ID: ad13k1l2m3n4
Revises: ac13j1k2l3m4
Create Date: 2026-08-21

Phase 13K — Organization Actions: an append-only record that the
organization, as an entity, did something. The clean hook the spec asks
for instead of a giant hardcoded per-action condition chain.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ad13k1l2m3n4"
down_revision: Union[str, None] = "ac13j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_actions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=True),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("organization_actions")
