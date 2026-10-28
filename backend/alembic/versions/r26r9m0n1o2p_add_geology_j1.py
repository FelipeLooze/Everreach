"""Opt-in J1 geological units and finite experimental mineral deposits."""
from alembic import op
import sqlalchemy as sa

revision = "r26r9m0n1o2p"
down_revision = "q25q8l9m0n1o"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_geology_plans",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_terrain_plans.campaign_id"), primary_key=True),
        sa.Column("geology_version", sa.Integer(), nullable=False), sa.Column("signature", sa.String(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False), sa.Column("baseline_checksum", sa.String(), nullable=False))
    op.create_table("genesis_geological_units",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_geology_plans.campaign_id"), primary_key=True),
        sa.Column("unit_id", sa.String(), primary_key=True), sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("baseline_checksum", sa.String(), nullable=False), sa.Column("changes", sa.JSON(), nullable=False))
    op.create_table("genesis_mineral_deposits", sa.Column("campaign_id", sa.String(), primary_key=True),
        sa.Column("deposit_id", sa.String(), primary_key=True), sa.Column("unit_id", sa.String(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False), sa.Column("baseline_checksum", sa.String(), nullable=False),
        sa.Column("remaining_units", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id", "unit_id"], ["genesis_geological_units.campaign_id", "genesis_geological_units.unit_id"]),
        sa.CheckConstraint("remaining_units >= 0", name="ck_geology_finite_remaining"))


def downgrade():
    op.drop_table("genesis_mineral_deposits")
    op.drop_table("genesis_geological_units")
    op.drop_table("genesis_geology_plans")
