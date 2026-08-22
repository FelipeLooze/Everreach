"""add indexed knowledge documents

Revision ID: bf18b1c2d3e4
Revises: be00s1u2r3v4
Create Date: 2026-08-22

Phase 18B — the long-term-knowledge retrieval index (app.ai.retrieval).
A search tool over authoritative Canon, never a second source of truth;
see app.db.models.knowledge_index.IndexedKnowledgeDocument.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "bf18b1c2d3e4"
down_revision: Union[str, None] = "be00s1u2r3v4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "indexed_knowledge_documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("document_type", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("embedding_json", sa.String(), nullable=True),
        sa.Column("occurred_world_minute", sa.Integer(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("source_version", sa.String(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_indexed_doc_campaign_source",
        "indexed_knowledge_documents",
        ["campaign_id", "source_type", "source_id"],
    )
    op.create_index(
        "ix_indexed_doc_campaign_current",
        "indexed_knowledge_documents",
        ["campaign_id", "is_current"],
    )


def downgrade() -> None:
    op.drop_index("ix_indexed_doc_campaign_current", table_name="indexed_knowledge_documents")
    op.drop_index("ix_indexed_doc_campaign_source", table_name="indexed_knowledge_documents")
    op.drop_table("indexed_knowledge_documents")
