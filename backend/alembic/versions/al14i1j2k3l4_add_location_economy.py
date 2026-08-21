"""add location economy

Revision ID: al14i1j2k3l4
Revises: ak14h1i2j3k4
Create Date: 2026-08-21

Phase 14I — Local Economy: a settlement's broad economic character
(POOR/MODEST/PROSPEROUS/WEALTHY), reusing the existing Location model
rather than a new "settlement" entity. Deliberately NOT a price
multiplier anywhere — see app.game.economy.local_economy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "al14i1j2k3l4"
down_revision: Union[str, None] = "ak14h1i2j3k4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "location_economies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=False),
        sa.Column("wealth_band", sa.String(), nullable=False, server_default="MODEST"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("location_id", name="uq_location_economy_location"),
    )


def downgrade() -> None:
    op.drop_table("location_economies")
