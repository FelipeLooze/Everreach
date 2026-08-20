"""add resource growth and player luck

Revision ID: e8i1f2a3b4c5
Revises: d8h1e2f3a4b5
Create Date: 2026-08-20
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "e8i1f2a3b4c5"
down_revision: Union[str, None] = "d8h1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    definitions = sa.table(
        "attribute_definitions",
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        definitions,
        [
            {
                "key": "LUCK",
                "name": "Sorte",
                "description": (
                    "Influência excepcional do acaso em situações "
                    "realmente incertas. Exclusiva do protagonista."
                ),
            }
        ],
    )

    connection = op.get_bind()
    character_ids = [
        row[0]
        for row in connection.execute(sa.text("SELECT id FROM characters"))
    ]
    character_attributes = sa.table(
        "character_attributes",
        sa.column("id", sa.String()),
        sa.column("character_id", sa.String()),
        sa.column("key", sa.String()),
        sa.column("value", sa.Integer()),
        sa.column("development", sa.Float()),
    )
    if character_ids:
        op.bulk_insert(
            character_attributes,
            [
                {
                    "id": f"attr_{uuid4().hex[:12]}",
                    "character_id": character_id,
                    "key": "LUCK",
                    "value": 10,
                    "development": 0.0,
                }
                for character_id in character_ids
            ],
        )

    op.create_table(
        "character_resource_growth",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("resource_key", sa.String(), nullable=False),
        sa.Column("development", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "resource_key",
            name="uq_character_resource_growth",
        ),
    )
    op.create_table(
        "resource_growth_evidence_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("resource_key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("contributing_attribute_key", sa.String(), nullable=True),
        sa.Column("evidence_key", sa.String(), nullable=False),
        sa.Column("context_key", sa.String(), nullable=False),
        sa.Column("base_amount", sa.Float(), nullable=False),
        sa.Column("awarded_amount", sa.Float(), nullable=False),
        sa.Column("repetition_count", sa.Integer(), nullable=False),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(
            ["contributing_attribute_key"], ["attribute_definitions.key"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resource_growth_evidence_character_key_time",
        "resource_growth_evidence_records",
        ["character_id", "resource_key", "world_minute"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resource_growth_evidence_character_key_time",
        table_name="resource_growth_evidence_records",
    )
    op.drop_table("resource_growth_evidence_records")
    op.drop_table("character_resource_growth")
    op.execute("DELETE FROM character_attributes WHERE key = 'LUCK'")
    op.execute("DELETE FROM attribute_definitions WHERE key = 'LUCK'")
