"""add class foundation

Revision ID: a8e1b2c3d4e5
Revises: f8c1d2e3a4b5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a8e1b2c3d4e5"
down_revision: Union[str, None] = "f8c1d2e3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "class_definitions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "name",
            name="uq_class_definition_campaign_name",
        ),
    )

    with op.batch_alter_table("characters") as batch_op:
        batch_op.add_column(
            sa.Column("active_class_id", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_character_active_class",
            "class_definitions",
            ["active_class_id"],
            ["id"],
        )

    op.create_table(
        "character_class_offers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("class_definition_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(
            ["class_definition_id"],
            ["class_definitions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "class_definition_id",
            name="uq_character_class_offer",
        ),
    )


def downgrade() -> None:
    op.drop_table("character_class_offers")
    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_constraint(
            "fk_character_active_class",
            type_="foreignkey",
        )
        batch_op.drop_column("active_class_id")
    op.drop_table("class_definitions")
