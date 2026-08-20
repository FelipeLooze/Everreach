"""add combat armor and resistances

Revision ID: r9k1l2m3n4o5
Revises: q9j1k2l3m4n5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r9k1l2m3n4o5"
down_revision: Union[str, None] = "q9j1k2l3m4n5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_combat_profiles",
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("slot", sa.String(), nullable=False),
        sa.Column("armor_rating", sa.Integer(), nullable=False),
        sa.Column("resistances_json", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.PrimaryKeyConstraint("item_id"),
    )
    op.create_table(
        "actor_combat_defenses",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("armor_rating", sa.Integer(), nullable=False),
        sa.Column("resistances_json", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_type",
            "actor_id",
            name="uq_actor_combat_defense_identity",
        ),
    )
    op.create_index(
        "ix_actor_combat_defense_identity",
        "actor_combat_defenses",
        ["actor_type", "actor_id"],
    )
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "damage_type",
                sa.String(),
                nullable=False,
                server_default="PHYSICAL",
            )
        )
        batch_op.add_column(
            sa.Column("damage_before_mitigation", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("armor_mitigation", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("resistance_mitigation", sa.Integer(), nullable=True)
        )
    with op.batch_alter_table("combat_technique_profiles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "damage_type",
                sa.String(),
                nullable=False,
                server_default="PHYSICAL",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("combat_technique_profiles") as batch_op:
        batch_op.drop_column("damage_type")
    with op.batch_alter_table("combat_actions") as batch_op:
        batch_op.drop_column("resistance_mitigation")
        batch_op.drop_column("armor_mitigation")
        batch_op.drop_column("damage_before_mitigation")
        batch_op.drop_column("damage_type")
    op.drop_index(
        "ix_actor_combat_defense_identity",
        table_name="actor_combat_defenses",
    )
    op.drop_table("actor_combat_defenses")
    op.drop_table("item_combat_profiles")
