"""add quest objective prerequisites

Revision ID: r12m1n2o3p4q
Revises: q12c1d2e3f4g5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r12m1n2o3p4q"
down_revision: str | None = "q12c1d2e3f4g5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("quest_objectives") as batch_op:
        batch_op.add_column(
            sa.Column("prerequisite_objective_id", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_quest_objectives_prerequisite",
            "quest_objectives",
            ["prerequisite_objective_id"],
            ["id"],
        )

    # Worlds created before this migration already contain the two initial
    # contracts. Preserve their intended ordering instead of only fixing new
    # campaigns.
    op.execute(
        sa.text(
            """
            UPDATE quest_objectives
            SET prerequisite_objective_id = (
                SELECT previous.id
                FROM quest_objectives AS previous
                WHERE previous.quest_id = quest_objectives.quest_id
                  AND previous."order" = 0
                LIMIT 1
            )
            WHERE quest_objectives."order" = 1
              AND quest_objectives.quest_id IN (
                  SELECT quests.id
                  FROM quests
                  WHERE quests.name IN (
                      'Relato da Primeira Chegada',
                      'Ronda dos Avisos'
                  )
              )
            """
        )
    )

    # Old saves used "Name: description" as the existence fact, and reveal
    # required every capitalized word of the description. Rewrite to the
    # current shape (job vocabulary + quoted title + description); reveal is
    # now matched on the quoted title alone.
    op.execute(
        sa.text(
            """
            UPDATE knowledge_facts
            SET statement = 'Há trabalho disponível, um contrato ou missão chamado "' || (
                SELECT quests.name
                FROM quests
                WHERE knowledge_facts.subject = 'quest:' || quests.id
                LIMIT 1
            ) || '": ' || (
                SELECT quests.description
                FROM quests
                WHERE knowledge_facts.subject = 'quest:' || quests.id
                LIMIT 1
            )
            WHERE knowledge_facts.fact_key LIKE 'quest:%\\:exists'
              AND EXISTS (
                  SELECT 1
                  FROM quests
                  WHERE knowledge_facts.subject = 'quest:' || quests.id
              )
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("quest_objectives") as batch_op:
        batch_op.drop_constraint(
            "fk_quest_objectives_prerequisite", type_="foreignkey"
        )
        batch_op.drop_column("prerequisite_objective_id")
