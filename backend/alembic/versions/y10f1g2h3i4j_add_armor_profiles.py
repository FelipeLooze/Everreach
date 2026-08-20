"""add body coverage and differentiated physical armor

Revision ID: y10f1g2h3i4j
Revises: x10e1f2g3h4i
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "y10f1g2h3i4j"
down_revision: Union[str, None] = "x10e1f2g3h4i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_armor_profiles",
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("coverage_json", sa.String(), nullable=False),
        sa.Column("physical_protections_json", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("item_id"),
    )
    op.execute(
        """
        INSERT INTO item_armor_profiles
            (item_id, coverage_json, physical_protections_json)
        SELECT item_id,
            CASE slot
                WHEN 'HEAD' THEN '["HEAD"]'
                WHEN 'HANDS' THEN '["HANDS"]'
                WHEN 'LEGS' THEN '["LEGS"]'
                WHEN 'FEET' THEN '["FEET"]'
                ELSE '["TORSO"]'
            END,
            '{"BLUNT":' || armor_rating || ',"PIERCE":' || armor_rating ||
            ',"SLASH":' || armor_rating || '}'
        FROM item_combat_profiles
        WHERE armor_rating > 0
        """
    )
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_constraint("ck_combat_action_weapon_mechanics", type_="check")
        batch_op.add_column(sa.Column("target_body_area", sa.String(), nullable=True))
    op.execute(
        "UPDATE combat_actions SET physical_damage_profile = 'BLUNT', "
        "target_body_area = 'TORSO' WHERE damage_type = 'PHYSICAL'"
    )
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.create_check_constraint(
            "ck_combat_action_weapon_mechanics",
            "weapon_instance_id IS NULL OR physical_damage_profile IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_combat_action_physical_semantics",
            "(damage_type = 'PHYSICAL' AND physical_damage_profile IS NOT NULL "
            "AND target_body_area IS NOT NULL) OR "
            "(damage_type <> 'PHYSICAL' AND physical_damage_profile IS NULL "
            "AND target_body_area IS NULL)",
        )
        batch_op.create_check_constraint(
            "ck_combat_action_target_body_area",
            "target_body_area IS NULL OR target_body_area IN "
            "('HEAD', 'TORSO', 'ARMS', 'HANDS', 'LEGS', 'FEET')",
        )


def downgrade() -> None:
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_constraint("ck_combat_action_target_body_area", type_="check")
        batch_op.drop_constraint("ck_combat_action_physical_semantics", type_="check")
        batch_op.drop_constraint("ck_combat_action_weapon_mechanics", type_="check")
    op.execute(
        "UPDATE combat_actions SET physical_damage_profile = NULL "
        "WHERE weapon_instance_id IS NULL"
    )
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_column("target_body_area")
        batch_op.create_check_constraint(
            "ck_combat_action_weapon_mechanics",
            "(weapon_instance_id IS NULL AND physical_damage_profile IS NULL) OR "
            "(weapon_instance_id IS NOT NULL AND physical_damage_profile IS NOT NULL)",
        )
    op.drop_table("item_armor_profiles")
