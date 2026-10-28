"""Explicit P1 policy and normalized child accounts of the W2 ledger."""
from alembic import op
import sqlalchemy as sa

revision = "q25q8l9m0n1o"
down_revision = "p24p7k8l9m0n"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_practical_hydrology",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_water_reconciliations.campaign_id"), primary_key=True),
        sa.Column("practical_version", sa.Integer(), nullable=False), sa.Column("signature", sa.String(), nullable=False),
        sa.Column("source_signature", sa.String(), nullable=False), sa.Column("config", sa.JSON(), nullable=False))
    op.create_table("genesis_local_water_accounts",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_practical_hydrology.campaign_id"), primary_key=True),
        sa.Column("account_id", sa.String(), primary_key=True), sa.Column("node", sa.Integer(), nullable=False),
        sa.Column("origin", sa.JSON(), nullable=False), sa.Column("origin_checksum", sa.String(), nullable=False),
        sa.Column("balance", sa.JSON(), nullable=False), sa.Column("state_checksum", sa.String(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False), sa.Column("head_id", sa.String(), nullable=False),
        sa.Column("last_minute", sa.BigInteger(), nullable=False))
    op.create_table("genesis_practical_capacity_use", sa.Column("campaign_id", sa.String(), primary_key=True),
        sa.Column("capacity_key", sa.String(), primary_key=True), sa.Column("revision_id", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id", "revision_id"], ["genesis_water_revisions.campaign_id", "genesis_water_revisions.revision_id"]))


def downgrade():
    op.drop_table("genesis_practical_capacity_use")
    op.drop_table("genesis_local_water_accounts")
    op.drop_table("genesis_practical_hydrology")
