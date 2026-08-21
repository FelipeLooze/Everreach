"""add organization notice and quest links

Revision ID: af13m1n2o3p4
Revises: ae13l1m2n3o4
Create Date: 2026-08-21

Phase 13M — Quest / Notice Integration. Conflict found and resolved by
extending, not bypassing, the existing Phase 12 architecture: Notice
(12I) only had author_npc_id — organizations did not exist yet when it
was built, so organizational authorship had no column to use. Quest
(12A) already had QuestSource.ORGANIZATION_REQUEST reserved for exactly
this case but no way to trace back to which organization. Both gaps are
completed here with one nullable FK each — no parallel notice/quest
system, no bypass of Phase 12's own authority over quests/objectives/
notices/participation.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "af13m1n2o3p4"
down_revision: Union[str, None] = "ae13l1m2n3o4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notices",
        sa.Column("author_organization_id", sa.String(), nullable=True),
    )
    op.add_column(
        "quests",
        sa.Column("sponsoring_organization_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quests", "sponsoring_organization_id")
    op.drop_column("notices", "author_organization_id")
