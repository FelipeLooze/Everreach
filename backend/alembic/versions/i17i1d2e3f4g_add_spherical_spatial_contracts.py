"""V2 sphere sectors and optional spatial bindings; v1 snapshots untouched."""
from alembic import op
import sqlalchemy as sa

revision = "i17i1d2e3f4g"
down_revision = "h16h1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("genesis_sphere_sectors",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_worlds.campaign_id"), primary_key=True),
        sa.Column("face", sa.Integer(), primary_key=True),
        sa.Column("x", sa.Integer(), primary_key=True),
        sa.Column("y", sa.Integer(), primary_key=True),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.CheckConstraint("face >= 0 AND face < 6 AND x >= 0 AND y >= 0", name="ck_sphere_sector_address"))
    op.create_table("location_spatial_anchors",
        sa.Column("location_id", sa.String(), sa.ForeignKey("locations.id"), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_worlds.campaign_id"), nullable=False),
        sa.Column("point", sa.JSON(), nullable=False))
    op.create_index("ix_location_spatial_anchors_campaign_id", "location_spatial_anchors", ["campaign_id"])
    op.create_table("entity_spatial_coverages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_worlds.campaign_id"), nullable=False),
        sa.Column("region_id", sa.String(), sa.ForeignKey("regions.id"), nullable=True),
        sa.Column("subregion_id", sa.String(), sa.ForeignKey("subregions.id"), nullable=True),
        sa.Column("face", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.CheckConstraint("(region_id IS NOT NULL AND subregion_id IS NULL) OR "
                           "(region_id IS NULL AND subregion_id IS NOT NULL)", name="ck_coverage_owner"),
        sa.CheckConstraint("face >= 0 AND face < 6 AND level >= 0 AND level <= 24 AND "
                           "x >= 0 AND y >= 0 AND x < (1 << level) AND y < (1 << level)",
                           name="ck_coverage_address"),
        sa.UniqueConstraint("region_id", "face", "level", "x", "y", name="uq_region_coverage_cell"),
        sa.UniqueConstraint("subregion_id", "face", "level", "x", "y", name="uq_subregion_coverage_cell"))
    op.create_index("ix_entity_spatial_coverages_campaign_id", "entity_spatial_coverages", ["campaign_id"])


def downgrade() -> None:
    op.drop_table("entity_spatial_coverages")
    op.drop_table("location_spatial_anchors")
    op.drop_table("genesis_sphere_sectors")
