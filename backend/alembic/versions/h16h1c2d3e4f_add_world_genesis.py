"""Add opt-in World Genesis snapshots without reinterpreting existing saves."""
from alembic import op
import sqlalchemy as sa

revision = "h16h1c2d3e4f"
down_revision = "g15g1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genesis_worlds",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("world_seed", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
    )
    op.create_table(
        "genesis_sectors",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_worlds.campaign_id"), primary_key=True),
        sa.Column("x", sa.Integer(), primary_key=True),
        sa.Column("y", sa.Integer(), primary_key=True),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("genesis_sectors")
    op.drop_table("genesis_worlds")
