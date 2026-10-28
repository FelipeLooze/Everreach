"""JR1 refinement of J1; finite deposits reuse the existing source table."""
from alembic import op
import sqlalchemy as sa

revision = "s27s0n1o2p3q"
down_revision = "r26r9m0n1o2p"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_regional_geology",
        sa.Column("campaign_id",sa.String(),sa.ForeignKey("genesis_geology_plans.campaign_id"),primary_key=True),
        sa.Column("regional_version",sa.Integer(),nullable=False),sa.Column("signature",sa.String(),nullable=False),
        sa.Column("descriptor",sa.JSON(),nullable=False),sa.Column("policy",sa.JSON(),nullable=False),
        sa.Column("policy_signature",sa.String(),nullable=False),sa.Column("source_checksum",sa.String(),nullable=False),
        sa.Column("write_epoch",sa.Integer(),nullable=False))
    op.create_table("genesis_regional_formations",sa.Column("campaign_id",sa.String(),
        sa.ForeignKey("genesis_regional_geology.campaign_id"),primary_key=True),
        sa.Column("formation_id",sa.String(),primary_key=True),sa.Column("parent_unit_id",sa.String(),nullable=False),
        sa.Column("baseline",sa.JSON(),nullable=False),sa.Column("baseline_checksum",sa.String(),nullable=False),
        sa.Column("changes",sa.JSON(),nullable=False),sa.ForeignKeyConstraint(["campaign_id","parent_unit_id"],
            ["genesis_geological_units.campaign_id","genesis_geological_units.unit_id"]))
    op.create_table("genesis_regional_sources",sa.Column("campaign_id",sa.String(),primary_key=True),
        sa.Column("deposit_id",sa.String(),primary_key=True),sa.Column("formation_id",sa.String(),nullable=False),
        sa.Column("material_id",sa.String(),nullable=False),sa.ForeignKeyConstraint(["campaign_id","formation_id"],
            ["genesis_regional_formations.campaign_id","genesis_regional_formations.formation_id"]),
        sa.ForeignKeyConstraint(["campaign_id","deposit_id"],["genesis_mineral_deposits.campaign_id","genesis_mineral_deposits.deposit_id"]),
        sa.UniqueConstraint("campaign_id","formation_id","material_id",name="uq_jr1_formation_material"))


def downgrade():
    op.drop_table("genesis_regional_sources")
    op.drop_table("genesis_regional_formations")
    op.drop_table("genesis_regional_geology")
