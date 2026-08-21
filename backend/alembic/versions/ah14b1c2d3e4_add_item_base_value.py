"""add item base value

Revision ID: ah14b1c2d3e4
Revises: ag14a1b2c3d4
Create Date: 2026-08-21

Phase 14B — Prices & Valuation: ItemDefinition gains an optional
reference value in Bronze — not a fixed universal price. Actual market
price (app.game.economy.pricing.resolve_market_price) adjusts this by
quality/condition, reusing Phase 10's own enums rather than duplicating
pricing logic inside the item system.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ah14b1c2d3e4"
down_revision: Union[str, None] = "ag14a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("base_value_bronze", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "base_value_bronze")
