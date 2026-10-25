"""Add persistent creature harvesting and loot buyer policies.

Revision ID: f15f1a2b3c4d
Revises: e15e1f2a3b4c
"""

from alembic import op
import sqlalchemy as sa


revision: str = "f15f1a2b3c4d"
down_revision: str | None = "e15e1f2a3b4c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "npcs",
        sa.Column("died_world_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "shops",
        sa.Column(
            "purchase_categories_json",
            sa.String(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.create_table(
        "creature_harvest_resolutions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("source_npc_id", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("species_key", sa.String(), nullable=False),
        sa.Column("harvest_method", sa.String(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("luck_value", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_key"),
        sa.UniqueConstraint(
            "campaign_id",
            "source_npc_id",
            "harvest_method",
            name="uq_creature_harvest_source_method",
        ),
    )


def downgrade() -> None:
    op.drop_table("creature_harvest_resolutions")
    op.drop_column("shops", "purchase_categories_json")
    op.drop_column("npcs", "died_world_minute")
