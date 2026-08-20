"""add layered simulation indexes

Revision ID: c4a6d9e217bf
Revises: ab80f9c90d62
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c4a6d9e217bf"
down_revision: Union[str, None] = "ab80f9c90d62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_npcs_campaign_location_alive",
        "npcs",
        ["campaign_id", "location_id", "alive"],
        unique=False,
    )
    op.create_index(
        "ix_simulated_players_campaign_location_status",
        "simulated_players",
        ["campaign_id", "location_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_simulated_players_campaign_location_status",
        table_name="simulated_players",
    )
    op.drop_index(
        "ix_npcs_campaign_location_alive",
        table_name="npcs",
    )
