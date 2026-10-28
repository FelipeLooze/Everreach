"""Additive opt-in resource authority and frozen lot weights; no old masses rewritten."""
from alembic import op
import sqlalchemy as sa
revision="v30v3q4r5s6t"
down_revision="u29u2p3q4r5s"
branch_labels=None
depends_on=None


def upgrade():
    op.add_column("item_instances",sa.Column("unit_weight_override",sa.Float(),nullable=True))
    op.add_column("item_instances",sa.Column("weight_authority",sa.String(),nullable=True))
    op.create_table("genesis_plant_resources",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_vegetation_plans.campaign_id"),primary_key=True),
        sa.Column("signature",sa.String(),nullable=False),sa.Column("descriptor",sa.JSON(),nullable=False),
        sa.Column("descriptor_checksum",sa.String(),nullable=False))


def downgrade():
    op.drop_table("genesis_plant_resources")
    with op.batch_alter_table("item_instances") as batch:
        batch.drop_column("weight_authority");batch.drop_column("unit_weight_override")
