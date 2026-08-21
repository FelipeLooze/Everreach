"""add organization assets and treasury

Revision ID: ac13j1k2l3m4
Revises: ab13i1j2k3l4
Create Date: 2026-08-21

Phase 13J — Organization Resources & Assets. Conflict found and
resolved, not silently worked around: ItemInstance.owner_type and
.location_type (Phase 10) are hard CHECK-constrained to
CHARACTER/NPC/NONE — extending that constraint to add ORGANIZATION would
be a Phase-10-level schema change, out of scope for Phase 13.
OrganizationAsset instead links an existing ItemInstance to its
beneficial organizational owner as a thin overlay, without touching
ItemInstance's own columns/constraints at all — the item's physical
placement, quality and durability stay entirely governed by the existing
Item system. treasury is a simple authoritative funds balance on
Organization itself — Phase 14 may deepen it later.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ac13j1k2l3m4"
down_revision: Union[str, None] = "ab13i1j2k3l4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("treasury", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_table(
        "organization_assets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("item_instance_id", sa.String(), nullable=False),
        sa.Column("acquired_world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["item_instance_id"], ["item_instances.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_instance_id", name="uq_organization_asset_item"),
    )


def downgrade() -> None:
    op.drop_table("organization_assets")
    op.drop_column("organizations", "treasury")
