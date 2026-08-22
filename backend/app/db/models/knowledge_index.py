from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class IndexedKnowledgeDocument(Base):
    """Phase 18B — a retrievable long-term-knowledge chunk (app.ai.retrieval).

    This is a SEARCH TOOL, never a second source of truth: source_type +
    source_id always point back at the authoritative row this text was
    generated from (Region/NPC/Organization/WorldEvent/...), so a consumer
    re-fetches current authoritative state after a semantic candidate is
    selected rather than trusting this row's prose directly. If this table
    ever disagrees with the database, the database wins.

    is_current distinguishes "the active document for this source+type"
    from a superseded one kept for historical retrieval (Phase 18M) — old
    documents are never deleted just because the world moved on, only
    flipped to is_current=False when Phase 18M's supersession explicitly
    replaces them.
    """

    __tablename__ = "indexed_knowledge_documents"
    __table_args__ = (
        Index(
            "ix_indexed_doc_campaign_source",
            "campaign_id",
            "source_type",
            "source_id",
        ),
        Index("ix_indexed_doc_campaign_current", "campaign_id", "is_current"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("idoc"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    document_type: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    # Phase 18H populates this (serialized float vector); NULL until then,
    # and reset to NULL whenever text is regenerated so a stale embedding
    # can never be scored against new text.
    embedding_json: Mapped[str | None] = mapped_column(String, nullable=True)
    # World-clock minute this document's fact occurred/became true — never
    # wall-clock time. NULL for documents with no single point-in-time
    # meaning (e.g. a Region's general geography).
    occurred_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    # Opaque fingerprint of the authoritative fields this text was built
    # from (e.g. an event id, or a hash of the source row's relevant
    # columns) — lets a future re-index pass detect "nothing changed,
    # skip" without re-deriving and re-comparing the full text.
    source_version: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
