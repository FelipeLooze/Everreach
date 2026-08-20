"""add authoritative weapon profiles and combat evidence

Revision ID: x10e1f2g3h4i
Revises: w10d1e2f3g4h
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "x10e1f2g3h4i"
down_revision: Union[str, None] = "w10d1e2f3g4h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_weapon_profiles",
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("weapon_family", sa.String(), nullable=False),
        sa.Column("damage_profiles_json", sa.String(), nullable=False),
        sa.Column("reach", sa.String(), nullable=False),
        sa.Column("hand_requirement", sa.String(), nullable=False),
        sa.CheckConstraint(
            "weapon_family IN ('DAGGER', 'KNIFE', 'SWORD', 'AXE', 'HAMMER', "
            "'MACE', 'SPEAR', 'POLEARM', 'BOW', 'CROSSBOW', 'SLING', "
            "'STAFF', 'CLUB')",
            name="ck_item_weapon_family",
        ),
        sa.CheckConstraint(
            "reach IN ('NORMAL', 'LONG', 'RANGED')",
            name="ck_item_weapon_reach",
        ),
        sa.CheckConstraint(
            "hand_requirement IN ('ONE_HAND', 'ONE_OR_TWO_HANDS', 'TWO_HANDS')",
            name="ck_item_weapon_hand_requirement",
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("item_id"),
    )
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.add_column(
            sa.Column("weapon_instance_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("physical_damage_profile", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_combat_action_weapon_instance",
            "item_instances",
            ["weapon_instance_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_combat_action_weapon_mechanics",
            "(weapon_instance_id IS NULL AND physical_damage_profile IS NULL) OR "
            "(weapon_instance_id IS NOT NULL AND physical_damage_profile IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_combat_action_physical_damage_profile",
            "physical_damage_profile IS NULL OR "
            "physical_damage_profile IN ('SLASH', 'PIERCE', 'BLUNT')",
        )


def downgrade() -> None:
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_constraint(
            "ck_combat_action_physical_damage_profile",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_combat_action_weapon_mechanics",
            type_="check",
        )
        batch_op.drop_constraint(
            "fk_combat_action_weapon_instance",
            type_="foreignkey",
        )
        batch_op.drop_column("physical_damage_profile")
        batch_op.drop_column("weapon_instance_id")
    op.drop_table("item_weapon_profiles")
