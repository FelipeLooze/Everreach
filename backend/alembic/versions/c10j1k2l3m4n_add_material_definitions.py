"""add extensible material definitions and item composition

Revision ID: c10j1k2l3m4n
Revises: b10i1j2k3l4m
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c10j1k2l3m4n"
down_revision: Union[str, None] = "b10i1j2k3l4m"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_definitions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("weight_factor", sa.Float(), nullable=False),
        sa.Column("wear_resistance", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "weight_factor > 0", name="ck_material_weight_factor_positive"
        ),
        sa.CheckConstraint(
            "wear_resistance > 0", name="ck_material_wear_resistance_positive"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
        sa.UniqueConstraint("name"),
    )
    op.bulk_insert(
        sa.table(
            "material_definitions",
            sa.column("id", sa.String()),
            sa.column("key", sa.String()),
            sa.column("name", sa.String()),
            sa.column("description", sa.String()),
            sa.column("weight_factor", sa.Float()),
            sa.column("wear_resistance", sa.Float()),
        ),
        [
            {"id": "material_iron", "key": "IRON", "name": "Ferro", "description": "Metal comum, pesado e estruturalmente confiável.", "weight_factor": 1.0, "wear_resistance": 1.0},
            {"id": "material_steel", "key": "STEEL", "name": "Aço", "description": "Liga resistente usada em ferramentas e equipamento.", "weight_factor": 1.0, "wear_resistance": 1.25},
            {"id": "material_bronze", "key": "BRONZE", "name": "Bronze", "description": "Liga relativamente pesada e de resistência moderada.", "weight_factor": 1.1, "wear_resistance": 0.9},
            {"id": "material_wood", "key": "WOOD", "name": "Madeira", "description": "Material leve e rígido de origem vegetal.", "weight_factor": 0.4, "wear_resistance": 0.65},
            {"id": "material_leather", "key": "LEATHER", "name": "Couro", "description": "Material orgânico flexível e moderadamente resistente.", "weight_factor": 0.5, "wear_resistance": 0.6},
            {"id": "material_wool", "key": "WOOL", "name": "Lã", "description": "Fibra leve adequada a vestimentas e acolchoamento.", "weight_factor": 0.25, "wear_resistance": 0.35},
            {"id": "material_linen", "key": "LINEN", "name": "Linho", "description": "Tecido vegetal leve e de resistência limitada.", "weight_factor": 0.2, "wear_resistance": 0.3},
        ],
    )
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.add_column(sa.Column("material_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_item_instance_material",
            "material_definitions",
            ["material_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("item_instances") as batch_op:
        batch_op.drop_constraint("fk_item_instance_material", type_="foreignkey")
        batch_op.drop_column("material_id")
    op.drop_table("material_definitions")
