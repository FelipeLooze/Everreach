"""add the villager who asks a request and its bronze reward

Starting village population, part 4 (2026-10-24).

Revision ID: d15d1e2f3a4b
Revises: c15c1d2e3f4a
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d15d1e2f3a4b"
down_revision: str | None = "c15c1d2e3f4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("quests") as batch_op:
        batch_op.add_column(sa.Column("giver_npc_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("reward_bronze", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_foreign_key("fk_quests_giver_npc_id_npcs", "npcs", ["giver_npc_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("quests") as batch_op:
        batch_op.drop_constraint("fk_quests_giver_npc_id_npcs", type_="foreignkey")
        batch_op.drop_column("reward_bronze")
        batch_op.drop_column("giver_npc_id")
