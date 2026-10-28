"""Opt-in HR1 configuration and progressively prepared regions."""
from alembic import op
import sqlalchemy as sa

revision = "k19k2f3g4h5i"
down_revision = "j18j1e2f3g4h"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_hydrology_refinements",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_hydrology_plans.campaign_id"), primary_key=True),
        sa.Column("refinement_version", sa.Integer(), nullable=False),
        sa.Column("hydrology_signature", sa.String(), nullable=False),
        sa.Column("hydrology_checksum", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False))
    op.create_table("genesis_hydrology_regions",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_hydrology_refinements.campaign_id"), primary_key=True),
        sa.Column("node", sa.Integer(), primary_key=True),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("baseline_checksum", sa.String(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.CheckConstraint("node >= 0 AND node < 6144", name="ck_hydrology_region_node"))


def downgrade():
    op.drop_table("genesis_hydrology_regions")
    op.drop_table("genesis_hydrology_refinements")
