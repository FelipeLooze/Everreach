"""add currency foundation

Revision ID: ag14a1b2c3d4
Revises: af13m1n2o3p4
Create Date: 2026-08-21

Phase 14A — Currency Foundation. Conflict found and resolved, not
silently left in place: Organization.treasury (Phase 13J) was a Float
column, mutated by plain += float accumulation — exactly the floating-
point money Phase 14A's own design rules forbid. Its migration's own
docstring already deferred real currency semantics to "Phase 14" —
converted here to Integer Bronze (the canonical smallest unit; 100
Bronze = 1 Silver, 100 Silver = 1 Gold), consistent with the new
CurrencyHolding table this migration also creates for
character/NPC/simulated-player money. SQLite requires batch mode to
alter a column's type.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ag14a1b2c3d4"
down_revision: Union[str, None] = "af13m1n2o3p4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "currency_holdings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("owner_type", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("container_item_instance_id", sa.String(), nullable=True),
        sa.Column("amount_bronze", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("amount_bronze >= 0", name="ck_currency_holding_non_negative"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["container_item_instance_id"], ["item_instances.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_type", "owner_id", "container_item_instance_id",
            name="uq_currency_holding_owner_container",
        ),
    )

    with op.batch_alter_table("organizations") as batch_op:
        batch_op.alter_column(
            "treasury",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
            server_default="0",
        )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.alter_column(
            "treasury",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
            server_default="0",
        )
    op.drop_table("currency_holdings")
