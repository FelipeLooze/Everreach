"""W1 opt-in plans and sector snapshots; leaves all previous payloads untouched."""
from alembic import op
import sqlalchemy as sa

revision = "m21m4h5i6j7k"
down_revision = "l20l3g4h5i6j"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_water_plans",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_climate_plans.campaign_id"),
                  sa.ForeignKey("genesis_hydrology_refinements.campaign_id"), primary_key=True),
        sa.Column("water_version", sa.Integer(), nullable=False), sa.Column("signature", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("hydrology_signature", sa.String(), nullable=False), sa.Column("hydrology_checksum", sa.String(), nullable=False),
        sa.Column("climate_signature", sa.String(), nullable=False), sa.Column("climate_checksum", sa.String(), nullable=False),
        sa.Column("hr_signature", sa.String(), nullable=False), sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("payload_checksum", sa.String(), nullable=False), sa.Column("plan", sa.JSON(), nullable=False))
    op.create_table("genesis_water_sectors",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_water_plans.campaign_id"), primary_key=True),
        sa.Column("face", sa.Integer(), primary_key=True), sa.Column("x", sa.Integer(), primary_key=True),
        sa.Column("y", sa.Integer(), primary_key=True), sa.Column("baseline_checksum", sa.String(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False), sa.Column("changes", sa.JSON(), nullable=False),
        sa.CheckConstraint("face >= 0 AND face < 6 AND x >= 0 AND y >= 0", name="ck_water_sector_address"))


def downgrade():
    op.drop_table("genesis_water_sectors")
    op.drop_table("genesis_water_plans")
