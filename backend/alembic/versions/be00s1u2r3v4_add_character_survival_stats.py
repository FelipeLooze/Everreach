"""add character survival stats

Revision ID: be00s1u2r3v4
Revises: bd17i1j2k3l4
Create Date: 2026-08-22

Survival (hunger/thirst) follow-up requested after Phase 17: adds
hunger_current/hunger_max/thirst_current/thirst_max and
survival_updated_at_minute to characters. Deliberately slow-draining —
see app.game.survival.service for decay rates and the ENDURANCE-scaled
max formula. No changes to any other table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "be00s1u2r3v4"
down_revision: Union[str, None] = "bd17i1j2k3l4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("hunger_current", sa.Float(), nullable=False, server_default="100.0"))
    op.add_column("characters", sa.Column("hunger_max", sa.Float(), nullable=False, server_default="100.0"))
    op.add_column("characters", sa.Column("thirst_current", sa.Float(), nullable=False, server_default="100.0"))
    op.add_column("characters", sa.Column("thirst_max", sa.Float(), nullable=False, server_default="100.0"))
    op.add_column("characters", sa.Column("survival_updated_at_minute", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("characters", "survival_updated_at_minute")
    op.drop_column("characters", "thirst_max")
    op.drop_column("characters", "thirst_current")
    op.drop_column("characters", "hunger_max")
    op.drop_column("characters", "hunger_current")
