"""add technique weapon requirement

Revision ID: j11e1f2g3h4i
Revises: i11d1e2f3g4h
Create Date: 2026-08-21

Phase 11E — Physical Techniques: a combat technique may require an
equipped weapon of a specific family (e.g. Lunging Thrust needs a sword).
NULL means no weapon requirement (an unarmed/bodily technique), preserving
current behavior for every existing profile.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j11e1f2g3h4i"
down_revision: Union[str, None] = "i11d1e2f3g4h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "combat_technique_profiles",
        sa.Column("required_weapon_family", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("combat_technique_profiles", "required_weapon_family")
