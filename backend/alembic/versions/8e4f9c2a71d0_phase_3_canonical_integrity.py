"""phase 3 canonical integrity and context lookup indexes

Revision ID: 8e4f9c2a71d0
Revises: 2c01f4b8a912
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op


revision: str = "8e4f9c2a71d0"
down_revision: Union[str, None] = "2c01f4b8a912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Older development databases may contain duplicate logical rows. Collapse
    # them before making the canon identity constraints enforceable.
    op.execute(
        """
        UPDATE knowledge_knowers
        SET fact_id = (
            SELECT MIN(f2.id)
            FROM knowledge_facts AS f1
            JOIN knowledge_facts AS f2
              ON f2.campaign_id = f1.campaign_id AND f2.fact_key = f1.fact_key
            WHERE f1.id = knowledge_knowers.fact_id
        )
        """
    )
    op.execute(
        """
        DELETE FROM knowledge_knowers
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM knowledge_knowers
            GROUP BY fact_id, knower_type, knower_id
        )
        """
    )
    op.execute(
        """
        DELETE FROM knowledge_facts
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM knowledge_facts
            GROUP BY campaign_id, fact_key
        )
        """
    )

    with op.batch_alter_table("knowledge_facts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_knowledge_fact_campaign_key", ["campaign_id", "fact_key"]
        )
    with op.batch_alter_table("knowledge_knowers") as batch_op:
        batch_op.create_unique_constraint(
            "uq_knowledge_knower_fact_identity",
            ["fact_id", "knower_type", "knower_id"],
        )

    op.create_index(
        "ix_knowledge_fact_campaign_subject",
        "knowledge_facts",
        ["campaign_id", "subject"],
    )
    op.create_index(
        "ix_knowledge_knower_identity",
        "knowledge_knowers",
        ["knower_type", "knower_id", "fact_id"],
    )
    op.create_index(
        "ix_location_connection_origin_active",
        "location_connections",
        ["from_location_id", "active"],
    )


def downgrade() -> None:
    op.drop_index("ix_location_connection_origin_active", table_name="location_connections")
    op.drop_index("ix_knowledge_knower_identity", table_name="knowledge_knowers")
    op.drop_index("ix_knowledge_fact_campaign_subject", table_name="knowledge_facts")
    with op.batch_alter_table("knowledge_knowers") as batch_op:
        batch_op.drop_constraint("uq_knowledge_knower_fact_identity", type_="unique")
    with op.batch_alter_table("knowledge_facts") as batch_op:
        batch_op.drop_constraint("uq_knowledge_fact_campaign_key", type_="unique")
