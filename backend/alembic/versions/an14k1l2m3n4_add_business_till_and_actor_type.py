"""add business till and actor type

Revision ID: an14k1l2m3n4
Revises: am14j1k2l3m4
Create Date: 2026-08-21

Phase 14K — Business Operations: a Business gets its own finite funds
(till_bronze), separate from its owner's personal or organizational
money — a business can run out of money independent of its owner being
broke, same principle Phase 14G already established for Shop.till_bronze.
EconomicActorType gains BUSINESS so app.game.economy.actors.
withdraw_from_actor/deposit_to_actor can move money for a business the
same uniform way they already do for characters/NPCs/organizations
(enum-only change, no schema impact from that half).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "an14k1l2m3n4"
down_revision: Union[str, None] = "am14j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("till_bronze", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("businesses", "till_bronze")
