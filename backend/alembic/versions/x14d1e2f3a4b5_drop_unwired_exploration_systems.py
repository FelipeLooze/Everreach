"""drop systems never wired into play: physical maps, expeditions, rumor accuracy

Simplification 2026-10-23. Nothing in the game created a physical map or an
expedition, and rumor_accuracy was written by rumors nobody started; the
code for all three is removed with this revision.

Revision ID: x14d1e2f3a4b5
Revises: w14c1d2e3f4a5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "x14d1e2f3a4b5"
down_revision: str | None = "w14c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("maps")
    op.drop_table("expeditions")
    with op.batch_alter_table("knowledge_facts") as batch_op:
        batch_op.drop_column("rumor_accuracy")


def downgrade() -> None:
    # Same shapes as bc17g1h2i3j4 / bd17i1j2k3l4 and the rumor column, so
    # earlier revisions can still drop them on their own downgrade.
    with op.batch_alter_table("knowledge_facts") as batch_op:
        batch_op.add_column(sa.Column("rumor_accuracy", sa.String(), nullable=True))
    op.create_table(
        "expeditions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("group_id", sa.String(), sa.ForeignKey("groups.id"), nullable=False, unique=True),
        sa.Column("purpose", sa.String(), nullable=False, server_default=""),
        sa.Column("target_subject_kind", sa.String(), nullable=True),
        sa.Column("target_entity_id", sa.String(), nullable=True),
        sa.Column("origin_location_id", sa.String(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PLANNED"),
        sa.Column("started_world_minute", sa.Integer(), nullable=True),
        sa.Column("resolved_world_minute", sa.Integer(), nullable=True),
    )
    op.create_table(
        "maps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("item_instance_id", sa.String(), sa.ForeignKey("item_instances.id"), nullable=False, unique=True),
        sa.Column("subject_kind", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("creator_type", sa.String(), nullable=False),
        sa.Column("creator_id", sa.String(), nullable=False),
        sa.Column("created_world_minute", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("content_json", sa.String(), nullable=False),
    )
