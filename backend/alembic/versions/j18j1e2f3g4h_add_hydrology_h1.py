"""Add opt-in H1 plans/corridors without changing formation or legacy saves."""
from alembic import op
import sqlalchemy as sa

revision = "j18j1e2f3g4h"
down_revision = "i17i1d2e3f4g"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("genesis_hydrology_plans",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_worlds.campaign_id"), primary_key=True),
        sa.Column("hydrology_version", sa.Integer(), nullable=False),
        sa.Column("source_signature", sa.String(), nullable=False),
        sa.Column("source_checksum", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("payload_checksum", sa.String(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False))
    op.create_table("genesis_hydrology_sectors",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_hydrology_plans.campaign_id"), primary_key=True),
        sa.Column("face", sa.Integer(), primary_key=True),
        sa.Column("x", sa.Integer(), primary_key=True),
        sa.Column("y", sa.Integer(), primary_key=True),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.CheckConstraint("face >= 0 AND face < 6 AND x >= 0 AND y >= 0", name="ck_hydrology_sector_address"))


def downgrade() -> None:
    op.drop_table("genesis_hydrology_sectors")
    op.drop_table("genesis_hydrology_plans")
