"""add map annotations

Revision ID: c1a2b3c4d5e6
Revises: bf18b1c2d3e4
Create Date: 2026-08-22

Phase 20J — Player Map Annotations. Purely user-owned map notes; see
app.db.models.map_annotation.MapAnnotation.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, None] = "bf18b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "map_annotations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("location_id", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_map_annotation_character",
        "map_annotations",
        ["character_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_map_annotation_character", table_name="map_annotations")
    op.drop_table("map_annotations")
