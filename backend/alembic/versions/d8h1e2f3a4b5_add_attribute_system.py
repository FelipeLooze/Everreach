"""add attribute system

Revision ID: d8h1e2f3a4b5
Revises: c8g1d2e3f4a5
Create Date: 2026-08-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8h1e2f3a4b5"
down_revision: Union[str, None] = "c8g1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ATTRIBUTE_CATALOG = [
    ("STRENGTH", "Força", "Capacidade física e potência."),
    ("AGILITY", "Agilidade", "Coordenação e precisão motora."),
    ("VITALITY", "Vitalidade", "Robustez e saúde física."),
    ("INTELLIGENCE", "Inteligência", "Raciocínio e compreensão técnica."),
    ("WISDOM", "Sabedoria", "Percepção, intuição e sensibilidade."),
    ("ENDURANCE", "Resistência", "Esforço prolongado e adversidade."),
]


def upgrade() -> None:
    op.create_table(
        "attribute_definitions",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    definitions = sa.table(
        "attribute_definitions",
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        definitions,
        [
            {"key": key, "name": name, "description": description}
            for key, name, description in ATTRIBUTE_CATALOG
        ],
    )

    with op.batch_alter_table("character_attributes") as batch_op:
        batch_op.add_column(sa.Column("key", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "development",
                sa.Float(),
                nullable=False,
                server_default="0",
            )
        )

    aliases = {
        "STRENGTH": ("Força", "Strength", "STRENGTH"),
        "AGILITY": ("Agilidade", "Agility", "AGILITY"),
        "VITALITY": ("Vitalidade", "Vitality", "VITALITY"),
        "INTELLIGENCE": ("Inteligência", "Intelligence", "INTELLIGENCE"),
        "WISDOM": ("Sabedoria", "Wisdom", "WISDOM"),
        "ENDURANCE": ("Resistência", "Endurance", "ENDURANCE"),
    }
    connection = op.get_bind()
    for key, names in aliases.items():
        connection.execute(
            sa.text(
                "UPDATE character_attributes SET key = :key "
                "WHERE name IN (:first, :second, :third)"
            ),
            {
                "key": key,
                "first": names[0],
                "second": names[1],
                "third": names[2],
            },
        )
    connection.execute(
        sa.text(
            "UPDATE character_attributes "
            "SET key = UPPER(REPLACE(TRIM(name), ' ', '_')) "
            "WHERE key IS NULL"
        )
    )
    connection.execute(
        sa.text(
            "INSERT OR IGNORE INTO attribute_definitions (key, name, description) "
            "SELECT DISTINCT key, name, '' FROM character_attributes"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM character_attributes WHERE id NOT IN ("
            "SELECT MIN(id) FROM character_attributes GROUP BY character_id, key"
            ")"
        )
    )

    with op.batch_alter_table("character_attributes") as batch_op:
        batch_op.alter_column("key", existing_type=sa.String(), nullable=False)
        batch_op.create_foreign_key(
            "fk_character_attribute_definition",
            "attribute_definitions",
            ["key"],
            ["key"],
        )
        batch_op.create_unique_constraint(
            "uq_character_attribute",
            ["character_id", "key"],
        )
        batch_op.drop_column("name")

    op.create_table(
        "attribute_evidence_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("attribute_key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("evidence_key", sa.String(), nullable=False),
        sa.Column("context_key", sa.String(), nullable=False),
        sa.Column("base_amount", sa.Float(), nullable=False),
        sa.Column("awarded_amount", sa.Float(), nullable=False),
        sa.Column("repetition_count", sa.Integer(), nullable=False),
        sa.Column("world_minute", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(
            ["attribute_key"], ["attribute_definitions.key"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attribute_evidence_character_key_time",
        "attribute_evidence_records",
        ["character_id", "attribute_key", "world_minute"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attribute_evidence_character_key_time",
        table_name="attribute_evidence_records",
    )
    op.drop_table("attribute_evidence_records")
    with op.batch_alter_table("character_attributes") as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(), nullable=True))
    op.execute(
        "UPDATE character_attributes SET name = ("
        "SELECT name FROM attribute_definitions "
        "WHERE attribute_definitions.key = character_attributes.key)"
    )
    with op.batch_alter_table("character_attributes") as batch_op:
        batch_op.alter_column("name", existing_type=sa.String(), nullable=False)
        batch_op.drop_constraint("uq_character_attribute", type_="unique")
        batch_op.drop_constraint(
            "fk_character_attribute_definition",
            type_="foreignkey",
        )
        batch_op.drop_column("development")
        batch_op.drop_column("key")
    op.drop_table("attribute_definitions")
