"""add technique lineage

Revision ID: k11f1g2h3i4j
Revises: j11e1f2g3h4i
Create Date: 2026-08-21

Phase 11H — Technique Evolution & Variants: a technique may optionally
record which existing technique it emerged as a variant of. Provenance
only — never a mechanical gate on learning, using, or recognizing it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k11f1g2h3i4j"
down_revision: Union[str, None] = "j11e1f2g3h4i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("techniques") as batch_op:
        batch_op.add_column(
            sa.Column("parent_technique_id", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_technique_parent_technique",
            "techniques",
            ["parent_technique_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("techniques") as batch_op:
        batch_op.drop_constraint(
            "fk_technique_parent_technique",
            type_="foreignkey",
        )
        batch_op.drop_column("parent_technique_id")
