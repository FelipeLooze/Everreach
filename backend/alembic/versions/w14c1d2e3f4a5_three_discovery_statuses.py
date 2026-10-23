"""three discovery statuses: UNKNOWN, DISCOVERED, VISITED

RUMORED is folded into DISCOVERED and MAPPED into VISITED (simplification
2026-10-23); mapped_at, written only alongside MAPPED, goes away.

Revision ID: w14c1d2e3f4a5
Revises: v14b1c2d3e4f5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "w14c1d2e3f4a5"
down_revision: str | None = "v14b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("character_location_discoveries", "status"),
    ("regions", "discovery_status"),
    ("locations", "discovery_status"),
)


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.execute(f"UPDATE {table} SET {column} = 'DISCOVERED' WHERE {column} = 'RUMORED'")
        op.execute(f"UPDATE {table} SET {column} = 'VISITED' WHERE {column} = 'MAPPED'")
    with op.batch_alter_table("character_location_discoveries") as batch_op:
        batch_op.drop_column("mapped_at")


def downgrade() -> None:
    with op.batch_alter_table("character_location_discoveries") as batch_op:
        batch_op.add_column(sa.Column("mapped_at", sa.DateTime(), nullable=True))
