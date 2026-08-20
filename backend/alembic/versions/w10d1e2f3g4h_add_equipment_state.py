"""add authoritative physical equipment state

Revision ID: w10d1e2f3g4h
Revises: v10c1d2e3f4g
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "w10d1e2f3g4h"
down_revision: Union[str, None] = "v10c1d2e3f4g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_equipment_profiles",
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("allowed_slots_json", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("item_id"),
    )
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.add_column(sa.Column("equipped_slot", sa.String(), nullable=True))

    # Phase 9 called torso coverage BODY. Preserve its profiles while adopting
    # the physical slot vocabulary introduced by Phase 10D.
    op.execute("UPDATE item_combat_profiles SET slot = 'TORSO' WHERE slot = 'BODY'")
    op.execute(
        "INSERT INTO item_equipment_profiles (item_id, allowed_slots_json) "
        "SELECT item_id, '[\"' || slot || '\"]' FROM item_combat_profiles"
    )
    op.execute(
        "INSERT INTO item_equipment_profiles (item_id, allowed_slots_json) "
        "SELECT DISTINCT definition_id, '[\"BACK\"]' FROM item_instances "
        "WHERE location_type = 'CHARACTER_EQUIPPED' AND definition_id NOT IN "
        "(SELECT item_id FROM item_equipment_profiles)"
    )
    op.execute(
        "UPDATE item_instances SET equipped_slot = COALESCE("
        "(SELECT item_combat_profiles.slot FROM item_combat_profiles "
        "WHERE item_combat_profiles.item_id = item_instances.definition_id), "
        "'BACK') WHERE location_type = 'CHARACTER_EQUIPPED'"
    )

    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.create_check_constraint(
            "ck_item_instance_equipped_slot",
            "(location_type = 'CHARACTER_EQUIPPED' AND equipped_slot IS NOT NULL) OR "
            "(location_type <> 'CHARACTER_EQUIPPED' AND equipped_slot IS NULL)",
        )
        batch_op.create_check_constraint(
            "ck_item_instance_equipment_slot_value",
            "equipped_slot IS NULL OR equipped_slot IN "
            "('HEAD', 'TORSO', 'LEGS', 'FEET', 'HANDS', 'MAIN_HAND', "
            "'OFF_HAND', 'BOTH_HANDS', 'BACK', 'WAIST', 'ACCESSORY')",
        )
        batch_op.create_index(
            "uq_item_instance_character_equipment_slot",
            ["location_type", "location_ref", "equipped_slot"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.drop_index("uq_item_instance_character_equipment_slot")
        batch_op.drop_constraint(
            "ck_item_instance_equipment_slot_value",
            type_="check",
        )
        batch_op.drop_constraint("ck_item_instance_equipped_slot", type_="check")
        batch_op.drop_column("equipped_slot")
    op.drop_table("item_equipment_profiles")
    op.execute("UPDATE item_combat_profiles SET slot = 'BODY' WHERE slot = 'TORSO'")
