"""add action checkpoints

Revision ID: m0k1l2m3n4o5
Revises: l0j1k2l3m4n5
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "m0k1l2m3n4o5"
down_revision: str | None = "l0j1k2l3m4n5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_checkpoints",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("player_text", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("post_fingerprint", sa.String(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=False, server_default=""),
        sa.Column("mechanical_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="CAPTURING"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("undone_at", sa.DateTime(), nullable=True),
        sa.Column("undo_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_checkpoints_campaign_id",
        "action_checkpoints",
        ["campaign_id"],
    )
    op.create_index(
        "ix_action_checkpoints_character_id",
        "action_checkpoints",
        ["character_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_action_checkpoints_character_id", table_name="action_checkpoints")
    op.drop_index("ix_action_checkpoints_campaign_id", table_name="action_checkpoints")
    op.drop_table("action_checkpoints")
