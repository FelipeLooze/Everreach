"""add visual identities

Revision ID: d2b3c4d5e6f7
Revises: c1a2b3c4d5e6
Create Date: 2026-08-23

Phase 21C — Structured Visual Specification Foundation. One reusable,
polymorphic table for every entity kind's stable/current visual data;
see app.db.models.visual_identity.VisualIdentity.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2b3c4d5e6f7"
down_revision: Union[str, None] = "c1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visual_identities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=True),
        sa.Column("subject_kind", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("stable_json", sa.String(), nullable=False),
        sa.Column("current_json", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "subject_kind", "subject_id", name="uq_visual_identity_subject"
        ),
    )
    op.create_index(
        "ix_visual_identity_subject",
        "visual_identities",
        ["subject_kind", "subject_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_visual_identity_subject", table_name="visual_identities")
    op.drop_table("visual_identities")
