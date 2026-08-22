"""add subregions and skeleton gate

Revision ID: aq15c1d2e3f4
Revises: ap15b1c2d3e4
Create Date: 2026-08-21

Phase 15C — Region Skeleton. New `subregions` table (macro subdivisions
of a massive Region — see Phase 15D for their rich identity fields).
Location gains a nullable subregion_id FK. Region gains skeleton_complete
(bool) as an explicit pipeline-stage gate: "WORLD MAP FIRST, ROOM DETAILS
LATER" — deep materialization (15N+) can assert the skeleton already
exists before it runs. Existing regions get skeleton_complete=False (they
predate subregions entirely, matching reality).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aq15c1d2e3f4"
down_revision: Union[str, None] = "ap15b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subregions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("region_id", sa.String(), sa.ForeignKey("regions.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation_seed", sa.Integer(), nullable=True),
    )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.add_column(sa.Column("subregion_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_locations_subregion_id", "subregions", ["subregion_id"], ["id"]
        )

    with op.batch_alter_table("regions") as batch_op:
        batch_op.add_column(
            sa.Column("skeleton_complete", sa.Boolean(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("regions") as batch_op:
        batch_op.drop_column("skeleton_complete")

    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_constraint("fk_locations_subregion_id", type_="foreignkey")
        batch_op.drop_column("subregion_id")

    op.drop_table("subregions")
