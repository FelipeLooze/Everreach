"""add combat technique profiles

Revision ID: n9g1h2i3j4k5
Revises: m9f1g2h3i4j5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "n9g1h2i3j4k5"
down_revision: Union[str, None] = "m9f1g2h3i4j5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("character_class_offers") as batch_op:
        batch_op.add_column(
            sa.Column("sequence_number", sa.Integer(), nullable=True)
        )
    op.create_table(
        "combat_technique_profiles",
        sa.Column("technique_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("attack_attribute", sa.String(), nullable=False),
        sa.Column("resource_key", sa.String(), nullable=False),
        sa.Column("resource_cost", sa.Float(), nullable=False),
        sa.Column("base_damage_dice", sa.Integer(), nullable=False),
        sa.Column("damage_die_sides", sa.Integer(), nullable=False),
        sa.Column("damage_attribute", sa.String(), nullable=False),
        sa.Column("condition_type", sa.String(), nullable=True),
        sa.Column("condition_duration_turns", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["technique_id"], ["techniques.id"]),
        sa.PrimaryKeyConstraint("technique_id"),
    )
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.add_column(sa.Column("technique_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("base_damage_dice", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("damage_die_sides", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("damage_attribute", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_combat_action_technique",
            "techniques",
            ["technique_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_constraint(
            "fk_combat_action_technique",
            type_="foreignkey",
        )
        batch_op.drop_column("damage_attribute")
        batch_op.drop_column("damage_die_sides")
        batch_op.drop_column("base_damage_dice")
        batch_op.drop_column("technique_id")
    op.drop_table("combat_technique_profiles")
    with op.batch_alter_table("character_class_offers") as batch_op:
        batch_op.drop_column("sequence_number")
