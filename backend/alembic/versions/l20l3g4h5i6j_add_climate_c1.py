"""Opt-in climatology C1; no changes to terrain or hydrology payloads."""
from alembic import op
import sqlalchemy as sa

revision = "l20l3g4h5i6j"
down_revision = "k19k2f3g4h5i"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_climate_plans",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_hydrology_plans.campaign_id"), primary_key=True),
        sa.Column("climate_version", sa.Integer(), nullable=False),
        sa.Column("source_signature", sa.String(), nullable=False),
        sa.Column("source_checksum", sa.String(), nullable=False),
        sa.Column("hydrology_signature", sa.String(), nullable=False),
        sa.Column("hydrology_checksum", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("payload_checksum", sa.String(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False))
    op.create_table("genesis_climate_sectors",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_climate_plans.campaign_id"), primary_key=True),
        sa.Column("face", sa.Integer(), primary_key=True),
        sa.Column("x", sa.Integer(), primary_key=True),
        sa.Column("y", sa.Integer(), primary_key=True),
        sa.Column("baseline_checksum", sa.String(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.CheckConstraint("face >= 0 AND face < 6 AND x >= 0 AND y >= 0", name="ck_climate_sector_address"))


def downgrade():
    op.drop_table("genesis_climate_sectors")
    op.drop_table("genesis_climate_plans")
