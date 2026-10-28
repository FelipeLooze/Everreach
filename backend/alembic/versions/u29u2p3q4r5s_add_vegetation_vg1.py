"""Explicit Vg1 tables. No campaign is activated or rewritten by this migration."""
from alembic import op
import sqlalchemy as sa

revision="u29u2p3q4r5s"
down_revision="t28t1o2p3q4r"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("genesis_vegetation_plans",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_environment_plans.campaign_id"),primary_key=True),
        sa.Column("signature",sa.String(),nullable=False),sa.Column("descriptor",sa.JSON(),nullable=False),
        sa.Column("descriptor_checksum",sa.String(),nullable=False),sa.Column("write_epoch",sa.Integer(),nullable=False))
    op.create_table("genesis_vegetation_communities",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_vegetation_plans.campaign_id"),primary_key=True),
        sa.Column("community_id",sa.String(),primary_key=True),sa.Column("baseline",sa.JSON(),nullable=False),
        sa.Column("baseline_checksum",sa.String(),nullable=False))
    op.create_table("genesis_plant_individuals",
        sa.Column("campaign_id",sa.String(),primary_key=True),sa.Column("individual_id",sa.String(),primary_key=True),
        sa.Column("community_id",sa.String(),nullable=False),sa.Column("baseline",sa.JSON(),nullable=False),
        sa.Column("baseline_checksum",sa.String(),nullable=False),sa.Column("state",sa.JSON(),nullable=False),
        sa.Column("state_checksum",sa.String(),nullable=False),
        sa.ForeignKeyConstraint(["campaign_id","community_id"],["genesis_vegetation_communities.campaign_id","genesis_vegetation_communities.community_id"]))
    op.create_index("ix_genesis_plant_individuals_community_id","genesis_plant_individuals",["community_id"])
    op.create_table("genesis_plant_actions",
        sa.Column("campaign_id",sa.String(),primary_key=True),sa.Column("action_id",sa.String(),primary_key=True),
        sa.Column("individual_id",sa.String(),nullable=False),sa.Column("actor_id",sa.String(),sa.ForeignKey("characters.id"),nullable=False),
        sa.Column("receipt",sa.JSON(),nullable=False),sa.Column("receipt_checksum",sa.String(),nullable=False),
        sa.ForeignKeyConstraint(["campaign_id","individual_id"],["genesis_plant_individuals.campaign_id","genesis_plant_individuals.individual_id"]))
    op.create_table("genesis_botanical_tool_certificates",
        sa.Column("item_id",sa.String(),sa.ForeignKey("item_tool_profiles.item_id"),primary_key=True),
        sa.Column("certificate",sa.JSON(),nullable=False),sa.Column("certificate_checksum",sa.String(),nullable=False))


def downgrade():
    for table in ("genesis_botanical_tool_certificates","genesis_plant_actions","genesis_plant_individuals",
                  "genesis_vegetation_communities","genesis_vegetation_plans"):
        op.drop_table(table)
