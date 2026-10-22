"""make quests playable end to end

Revision ID: p12b1c2d3e4f5
Revises: o11a1b2c3d4e5
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

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

    # Existing saves already have their initial settlement package, so the
    # schema change alone would leave their boards empty forever. Reuse the
    # same idempotent world-content builder used by fresh campaigns.
    from app.db.models.campaign import Campaign
    from app.game.quests.initial_content import (
        ensure_initial_quest_opportunities_for_campaign,
    )

    session = Session(bind=op.get_bind())
    for (campaign_id,) in session.query(Campaign.id).all():
        ensure_initial_quest_opportunities_for_campaign(session, campaign_id)
    session.flush()


def downgrade() -> None:
    with op.batch_alter_table("character_quests") as batch_op:
        batch_op.drop_column("reward_granted")
    with op.batch_alter_table("quests") as batch_op:
        batch_op.drop_column("xp_reward")
