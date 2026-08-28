"""add lazy economic canon values

Revision ID: k9i0j1k2l3m4
Revises: j8h9i0j1k2l3
Create Date: 2026-08-28

Additive and save-compatible: existing item base values remain authoritative;
existing campaigns simply have no lazily materialized rows yet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k9i0j1k2l3m4"
down_revision: Union[str, None] = "j8h9i0j1k2l3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "economic_canon_values",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("canonical_key", sa.String(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=True),
        sa.Column("provider_type", sa.String(), nullable=True),
        sa.Column("provider_id", sa.String(), nullable=True),
        sa.Column("classification", sa.String(), nullable=False),
        sa.Column("base_price_bronze", sa.Integer(), nullable=True),
        sa.Column("provenance", sa.String(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "classification IN ('MARKET_PRICE', 'NOT_FOR_SALE', "
            "'NO_ESTABLISHED_MARKET', 'NEGOTIATED_ONLY', 'UNIQUE_OR_PRICELESS')",
            name="ck_economic_value_classification",
        ),
        sa.CheckConstraint(
            "provenance IN ('SEEDED', 'DETERMINISTIC', 'LLM_PROPOSED', "
            "'CRAFT_DERIVED', 'WORLD_EVENT', 'CANON_OVERRIDE')",
            name="ck_economic_value_provenance",
        ),
        sa.CheckConstraint(
            "(classification = 'MARKET_PRICE' AND base_price_bronze IS NOT NULL "
            "AND base_price_bronze > 0) OR "
            "(classification <> 'MARKET_PRICE' AND base_price_bronze IS NULL)",
            name="ck_economic_value_price_shape",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_key", name="uq_economic_canon_value_key"),
    )
    op.create_index(
        "ix_economic_value_campaign_subject",
        "economic_canon_values",
        ["campaign_id", "subject_type", "subject_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_economic_value_campaign_subject", table_name="economic_canon_values")
    op.drop_table("economic_canon_values")
