"""make quests playable end to end

Revision ID: p12b1c2d3e4f5
Revises: o11a1b2c3d4e5
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "p12b1c2d3e4f5"
down_revision: str | None = "o11a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("quests") as batch_op:
        batch_op.add_column(
            sa.Column("xp_reward", sa.Float(), nullable=False, server_default="0.0")
        )
    with op.batch_alter_table("character_quests") as batch_op:
        batch_op.add_column(
            sa.Column("reward_granted", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    # Content backfill for existing saves happens at runtime
    # (engine.resolve_action -> ensure_initial_quest_opportunities_for_campaign),
    # not here: run from a migration it used today's ORM models against the
    # schema of THIS revision, so any save older than Phase 13 failed to
    # upgrade ("no such column: organizations.focus").


def downgrade() -> None:
    with op.batch_alter_table("character_quests") as batch_op:
        batch_op.drop_column("reward_granted")
    with op.batch_alter_table("quests") as batch_op:
        batch_op.drop_column("xp_reward")
