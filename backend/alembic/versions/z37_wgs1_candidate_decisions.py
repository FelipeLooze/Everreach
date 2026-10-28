"""Persist WGS1-v2 candidate eligibility decisions without altering v1 rows."""
from alembic import op
import sqlalchemy as sa

revision = "z37_wgs1_candidate_decisions"
down_revision = "z36_genesis_local_formations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "genesis_formation_candidates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("stable_key", sa.String(), nullable=False),
        sa.Column("archetype_id", sa.String(), nullable=False),
        sa.Column("generator_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.UniqueConstraint("campaign_id", "stable_key", name="uq_formation_candidate_key"),
        sa.CheckConstraint("status IN ('accepted', 'rejected', 'materialized')", name="ck_formation_candidate_status"),
    )
    op.create_index("ix_formation_candidate_campaign", "genesis_formation_candidates", ["campaign_id"])


def downgrade():
    op.drop_index("ix_formation_candidate_campaign", table_name="genesis_formation_candidates")
    op.drop_table("genesis_formation_candidates")
