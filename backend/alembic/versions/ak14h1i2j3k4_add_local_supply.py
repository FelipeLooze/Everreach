"""add local supply

Revision ID: ak14h1i2j3k4
Revises: aj14g1h2i3j4
Create Date: 2026-08-21

Phase 14H — Supply & Demand: a restrained local supply/demand indicator,
one row per (location, item definition), reusing the existing Location
model (Phase 4) as the settlement/local-market abstraction rather than
inventing a new "market" concept. 100 is baseline.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ak14h1i2j3k4"
down_revision: Union[str, None] = "aj14g1h2i3j4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_supply_levels",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=False),
        sa.Column("item_definition_id", sa.String(), nullable=False),
        sa.Column("supply_index", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("updated_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["item_definition_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "location_id", "item_definition_id", name="uq_local_supply_location_item"
        ),
    )


def downgrade() -> None:
    op.drop_table("local_supply_levels")
