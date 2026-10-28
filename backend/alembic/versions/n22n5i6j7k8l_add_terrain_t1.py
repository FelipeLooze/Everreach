"""Independent opt-in T1 descriptors and progressive fine tiles."""
from alembic import op
import sqlalchemy as sa

revision = "n22n5i6j7k8l"
down_revision = "m21m4h5i6j7k"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_terrain_plans",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_worlds.campaign_id"), primary_key=True),
        sa.Column("terrain_version", sa.Integer(), nullable=False), sa.Column("signature", sa.String(), nullable=False),
        sa.Column("source_checksum", sa.String(), nullable=False), sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False))
    op.create_table("genesis_terrain_tiles",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_terrain_plans.campaign_id"), primary_key=True),
        sa.Column("face", sa.Integer(), primary_key=True), sa.Column("level", sa.Integer(), primary_key=True),
        sa.Column("x", sa.BigInteger(), primary_key=True), sa.Column("y", sa.BigInteger(), primary_key=True),
        sa.Column("baseline_checksum", sa.String(), nullable=False), sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.CheckConstraint("face >= 0 AND face < 6 AND level >= 0 AND level <= 46 AND x >= 0 AND y >= 0",
                           name="ck_terrain_tile_address"))


def downgrade():
    op.drop_table("genesis_terrain_tiles")
    op.drop_table("genesis_terrain_plans")
