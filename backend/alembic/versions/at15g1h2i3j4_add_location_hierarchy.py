"""add location hierarchy

Revision ID: at15g1h2i3j4
Revises: as15f1g2h3i4
Create Date: 2026-08-21

Phase 15G — Settlement Internal Structure. Location gains a nullable
self-referential parent_location_id, reused for every level of the
Region > Subregion > Settlement > District > Location > Sublocation >
Interior hierarchy instead of a new model per level (spec: "Do not
require every level for every place"). MAJOR_CITY/CITY settlements get
district child-Locations; every settlement's services (inn, blacksmith,
temple...) attach as child Locations too — which services exist depends
on SettlementType (app.game.world.content_pools.SERVICES_BY_SETTLEMENT_TYPE).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "at15g1h2i3j4"
down_revision: Union[str, None] = "as15f1g2h3i4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("locations") as batch_op:
        batch_op.add_column(sa.Column("parent_location_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_locations_parent_location_id", "locations", ["parent_location_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_constraint("fk_locations_parent_location_id", type_="foreignkey")
        batch_op.drop_column("parent_location_id")
