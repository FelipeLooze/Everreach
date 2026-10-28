"""Persist sparse multi-cell WGS2 coverage relations."""
from alembic import op
import sqlalchemy as sa

revision = "z38_wgs2_coverage_cells"
down_revision = "z37_wgs1_candidate_decisions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "genesis_formation_coverage_cells",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("formation_id", sa.String(), sa.ForeignKey("genesis_natural_formations.id"), nullable=False),
        sa.Column("access_location_id", sa.String(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("face", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(), nullable=False),
        sa.Column("contract_checksum", sa.String(), nullable=False),
        sa.UniqueConstraint("campaign_id", "formation_id", "face", "level", "x", "y",
                            name="uq_formation_coverage_cell"),
        sa.CheckConstraint("face >= 0 AND face < 6 AND level >= 0 AND level <= 24 AND x >= 0 AND y >= 0",
                           name="ck_formation_coverage_cell_address"),
    )
    op.create_index("ix_formation_coverage_address", "genesis_formation_coverage_cells",
                    ["campaign_id", "face", "level", "x", "y"])


def downgrade():
    op.drop_index("ix_formation_coverage_address", table_name="genesis_formation_coverage_cells")
    op.drop_table("genesis_formation_coverage_cells")
