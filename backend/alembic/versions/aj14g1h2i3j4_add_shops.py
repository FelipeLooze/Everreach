"""add shops

Revision ID: aj14g1h2i3j4
Revises: ai14d1e2f3g4
Create Date: 2026-08-21

Phase 14G — Shops & Merchants: a real business operation, reusing Phase
10 item ownership for stock (operator_type restricted to CHARACTER/NPC,
the only owner types ItemInstance's own DB constraint allows) rather
than a separate item universe. till_bronze is the shop's own finite
funds, deliberately separate from the operator's personal money.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aj14g1h2i3j4"
down_revision: Union[str, None] = "ai14d1e2f3g4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shops",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("operator_type", sa.String(), nullable=False),
        sa.Column("operator_id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
        sa.Column("till_bronze", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_item_types_json", sa.String(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "shop_listings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("shop_id", sa.String(), nullable=False),
        sa.Column("item_instance_id", sa.String(), nullable=False),
        sa.Column("asking_price_bronze", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.ForeignKeyConstraint(["item_instance_id"], ["item_instances.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_instance_id", name="uq_shop_listing_item"),
    )


def downgrade() -> None:
    op.drop_table("shop_listings")
    op.drop_table("shops")
