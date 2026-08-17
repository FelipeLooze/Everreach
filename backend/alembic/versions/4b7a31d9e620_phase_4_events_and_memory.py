"""phase 4 events, owned memories and NPC relationships

Revision ID: 4b7a31d9e620
Revises: 8e4f9c2a71d0
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4b7a31d9e620"
down_revision: Union[str, None] = "8e4f9c2a71d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "world_events",
        sa.Column("importance", sa.Integer(), nullable=False, server_default="1"),
    )

    with op.batch_alter_table("memories") as batch_op:
        batch_op.add_column(
            sa.Column("owner_type", sa.String(), nullable=False, server_default="WORLD")
        )
        batch_op.add_column(
            sa.Column("owner_id", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("subject", sa.String(), nullable=False, server_default="world")
        )
        batch_op.add_column(sa.Column("source_event_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_memory_source_event", "world_events", ["source_event_id"], ["id"]
        )
        batch_op.create_unique_constraint(
            "uq_memory_owner_source_event",
            ["owner_type", "owner_id", "source_event_id"],
        )

    op.create_index(
        "ix_memory_relevant_lookup",
        "memories",
        ["campaign_id", "owner_type", "owner_id", "subject", "importance"],
    )
    op.create_table(
        "character_npc_relationships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("npc_id", sa.String(), nullable=False),
        sa.Column("familiarity", sa.Integer(), nullable=False),
        sa.Column("trust", sa.Integer(), nullable=False),
        sa.Column("affinity", sa.Integer(), nullable=False),
        sa.Column("last_interaction_minute", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["npc_id"], ["npcs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id", "npc_id", name="uq_character_npc_relationship_pair"
        ),
    )
    op.create_index(
        "ix_character_npc_relationship_campaign",
        "character_npc_relationships",
        ["campaign_id", "character_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_character_npc_relationship_campaign",
        table_name="character_npc_relationships",
    )
    op.drop_table("character_npc_relationships")
    op.drop_index("ix_memory_relevant_lookup", table_name="memories")
    with op.batch_alter_table("memories") as batch_op:
        batch_op.drop_constraint("uq_memory_owner_source_event", type_="unique")
        batch_op.drop_constraint("fk_memory_source_event", type_="foreignkey")
        batch_op.drop_column("source_event_id")
        batch_op.drop_column("subject")
        batch_op.drop_column("owner_id")
        batch_op.drop_column("owner_type")
    op.drop_column("world_events", "importance")
