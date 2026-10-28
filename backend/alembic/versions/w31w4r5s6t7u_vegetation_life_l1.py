"""Opt-in L1, no automatic campaign activation or resource rewrite."""
from alembic import op
import sqlalchemy as sa
revision="w31w4r5s6t7u"
down_revision="v30v3q4r5s6t"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("genesis_vegetation_life",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_plant_resources.campaign_id"),primary_key=True),
        sa.Column("signature",sa.String(),nullable=False),sa.Column("descriptor",sa.JSON(),nullable=False),
        sa.Column("descriptor_checksum",sa.String(),nullable=False),sa.Column("write_epoch",sa.Integer(),nullable=False))
    op.create_table("genesis_living_populations",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_vegetation_life.campaign_id"),primary_key=True),
        sa.Column("population_id",sa.String(),primary_key=True),sa.Column("community_id",sa.String(),nullable=False),
        sa.Column("species_id",sa.String(),nullable=False),sa.Column("data",sa.JSON(),nullable=False),sa.Column("data_checksum",sa.String(),nullable=False))
    op.create_index("ix_genesis_living_populations_community_id","genesis_living_populations",["community_id"])
    op.create_table("genesis_vegetation_life_events",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_vegetation_life.campaign_id"),primary_key=True),
        sa.Column("event_id",sa.String(),primary_key=True),sa.Column("population_id",sa.String(),nullable=False),
        sa.Column("due_minute",sa.Integer(),nullable=False),sa.Column("status",sa.String(),nullable=False),
        sa.Column("payload",sa.JSON(),nullable=False),sa.Column("payload_checksum",sa.String(),nullable=False))
    op.create_index("ix_life_event_due","genesis_vegetation_life_events",["campaign_id","population_id","status","due_minute"])


def downgrade():
    for name in ("genesis_vegetation_life_events","genesis_living_populations","genesis_vegetation_life"):op.drop_table(name)
