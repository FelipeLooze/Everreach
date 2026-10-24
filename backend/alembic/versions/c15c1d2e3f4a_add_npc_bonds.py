"""add bonds between NPCs (family, master and apprentice, friends, rivals)

Starting village population, part 3 (2026-10-24).

Revision ID: c15c1d2e3f4a
Revises: b15b1c2d3e4f
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c15c1d2e3f4a"
down_revision: str | None = "b15b1c2d3e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "npc_bonds",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("settlement_id", sa.String(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("first_npc_id", sa.String(), sa.ForeignKey("npcs.id"), nullable=False),
        sa.Column("second_npc_id", sa.String(), sa.ForeignKey("npcs.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=False, server_default=""),
    )
    op.create_index("ix_npc_bonds_campaign_id", "npc_bonds", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_npc_bonds_campaign_id", table_name="npc_bonds")
    op.drop_table("npc_bonds")
