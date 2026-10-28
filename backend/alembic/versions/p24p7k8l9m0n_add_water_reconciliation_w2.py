"""W2 opt-in local ledger and immutable revision/evidence history."""
from alembic import op
import sqlalchemy as sa

revision = "p24p7k8l9m0n"
down_revision = "o23o6j7k8l9m"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("genesis_water_reconciliations",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_water_plans.campaign_id"),
                  sa.ForeignKey("genesis_hydro_geometry_plans.campaign_id"), primary_key=True),
        sa.Column("water_version", sa.Integer(), nullable=False), sa.Column("signature", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False), sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("cutover_minute", sa.BigInteger(), nullable=False), sa.Column("write_epoch", sa.Integer(), nullable=False))
    op.create_table("genesis_water_domains",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_water_reconciliations.campaign_id"), primary_key=True),
        sa.Column("node", sa.Integer(), primary_key=True), sa.Column("head_id", sa.String(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False), sa.Column("last_minute", sa.BigInteger(), nullable=False),
        sa.Column("opening_checksum", sa.String(), nullable=False), sa.Column("state_checksum", sa.String(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False))
    op.create_table("genesis_water_reconciliation_evidence",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_water_reconciliations.campaign_id"), primary_key=True),
        sa.Column("evidence_key", sa.String(), primary_key=True), sa.Column("kind", sa.String(), nullable=False),
        sa.Column("node", sa.Integer(), nullable=False), sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False))
    op.create_table("genesis_water_revisions",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("genesis_water_reconciliations.campaign_id"), primary_key=True),
        sa.Column("revision_id", sa.String(), primary_key=True), sa.Column("operation_id", sa.String(), nullable=False),
        sa.Column("request_checksum", sa.String(), nullable=False), sa.Column("payload_checksum", sa.String(), nullable=False),
        sa.Column("logical_minute", sa.BigInteger(), nullable=False), sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.UniqueConstraint("campaign_id", "operation_id", name="uq_w2_operation"))
    op.create_table("genesis_water_transfers", sa.Column("campaign_id", sa.String(), primary_key=True),
        sa.Column("transfer_id", sa.String(), primary_key=True), sa.Column("revision_id", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id", "revision_id"], ["genesis_water_revisions.campaign_id", "genesis_water_revisions.revision_id"]))


def downgrade():
    for table in ("genesis_water_transfers", "genesis_water_revisions", "genesis_water_reconciliation_evidence",
                  "genesis_water_domains", "genesis_water_reconciliations"):
        op.drop_table(table)
