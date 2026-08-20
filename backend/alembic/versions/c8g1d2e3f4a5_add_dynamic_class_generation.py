"""add dynamic class generation

Revision ID: c8g1d2e3f4a5
Revises: b8f1c2d3e4f5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8g1d2e3f4a5"
down_revision: Union[str, None] = "b8f1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("class_definitions") as batch_op:
        batch_op.add_column(
            sa.Column("identity", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("theme", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("generation_key", sa.String(), nullable=True)
        )
    op.create_index(
        "uq_class_definition_campaign_generation_key",
        "class_definitions",
        ["campaign_id", "generation_key"],
        unique=True,
    )
    op.create_table(
        "class_definition_domains",
        sa.Column("class_definition_id", sa.String(), nullable=False),
        sa.Column("domain_key", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_definition_id"], ["class_definitions.id"]
        ),
        sa.ForeignKeyConstraint(["domain_key"], ["domain_definitions.key"]),
        sa.PrimaryKeyConstraint("class_definition_id", "domain_key"),
    )


def downgrade() -> None:
    op.drop_table("class_definition_domains")
    op.drop_index(
        "uq_class_definition_campaign_generation_key",
        table_name="class_definitions",
    )
    with op.batch_alter_table("class_definitions") as batch_op:
        batch_op.drop_column("generation_key")
        batch_op.drop_column("theme")
        batch_op.drop_column("identity")
