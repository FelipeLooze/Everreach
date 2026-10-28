"""Opt-in E1 environmental point fields; no existing save is reclassified."""
from alembic import op
import sqlalchemy as sa

revision="t28t1o2p3q4r"
down_revision="s27s0n1o2p3q"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("genesis_environment_plans",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_regional_geology.campaign_id"),primary_key=True),
        sa.Column("environment_version",sa.Integer(),nullable=False),sa.Column("signature",sa.String(),nullable=False),
        sa.Column("descriptor",sa.JSON(),nullable=False),sa.Column("descriptor_checksum",sa.String(),nullable=False),
        sa.Column("write_epoch",sa.Integer(),nullable=False))
    op.create_table("genesis_environment_points",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_environment_plans.campaign_id"),primary_key=True),
        sa.Column("probe_id",sa.String(),primary_key=True),sa.Column("formation_id",sa.String(),nullable=False),
        sa.Column("point",sa.JSON(),nullable=False),sa.Column("baseline",sa.JSON(),nullable=False),
        sa.Column("baseline_checksum",sa.String(),nullable=False),sa.Column("changes",sa.JSON(),nullable=False),
        sa.ForeignKeyConstraint(["campaign_id","formation_id"],["genesis_regional_formations.campaign_id","genesis_regional_formations.formation_id"]))


def downgrade():
    op.drop_table("genesis_environment_points")
    op.drop_table("genesis_environment_plans")
