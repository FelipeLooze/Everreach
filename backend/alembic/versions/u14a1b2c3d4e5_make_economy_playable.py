"""make Phase 14 economy playable

Revision ID: u14a1b2c3d4e5
Revises: t13b1c2d3e4f5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u14a1b2c3d4e5"
down_revision: str | None = "t13b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("shops") as batch_op:
        batch_op.add_column(sa.Column("business_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_shops_business_id_businesses", "businesses", ["business_id"], ["id"]
        )
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(
            sa.Column("work_minutes", sa.Integer(), nullable=False, server_default="120")
        )
        batch_op.add_column(sa.Column("profession_key", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("profession_name", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("profession_xp", sa.Float(), nullable=False, server_default="0.5")
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("profession_xp")
        batch_op.drop_column("profession_name")
        batch_op.drop_column("profession_key")
        batch_op.drop_column("work_minutes")
    with op.batch_alter_table("shops") as batch_op:
        batch_op.drop_constraint("fk_shops_business_id_businesses", type_="foreignkey")
        batch_op.drop_column("business_id")
