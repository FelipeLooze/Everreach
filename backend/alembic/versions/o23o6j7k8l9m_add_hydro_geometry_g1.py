"""G1 independent opt-in geometry; no terrain or water migrations."""
from alembic import op
import sqlalchemy as sa

revision = "o23o6j7k8l9m"
down_revision = "n22n5i6j7k8l"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_hydro_geometry_plans",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_terrain_plans.campaign_id"),
                  sa.ForeignKey("genesis_hydrology_refinements.campaign_id"), primary_key=True),
        sa.Column("geometry_version", sa.Integer(), nullable=False), sa.Column("signature", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False), sa.Column("plan", sa.JSON(), nullable=False))
    op.create_table("genesis_hydro_geometry_evidence",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_hydro_geometry_plans.campaign_id"), primary_key=True),
        sa.Column("request_id", sa.String(), primary_key=True), sa.Column("preparation_key", sa.String(), nullable=True),
        sa.Column("baseline_checksum", sa.String(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False), sa.Column("changes", sa.JSON(), nullable=False),
        sa.UniqueConstraint("campaign_id", "preparation_key", name="uq_g1_preparation"))


def downgrade():
    op.drop_table("genesis_hydro_geometry_evidence")
    op.drop_table("genesis_hydro_geometry_plans")
