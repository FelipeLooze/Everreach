from datetime import datetime, timezone
from app.core.ids import generate_id
from app.db.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)


class KnowledgeFact(Base):
    """A fact that is true in the world. Truth is separate from who knows it."""

    __tablename__ = "knowledge_facts"
    __table_args__ = (
        UniqueConstraint("campaign_id", "fact_key", name="uq_knowledge_fact_campaign_key"),
        Index("ix_knowledge_fact_campaign_subject", "campaign_id", "subject"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("fact"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String, default="world")
    fact_key: Mapped[str] = mapped_column(String, nullable=False)
    statement: Mapped[str] = mapped_column(String, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    social_priority: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

class KnowledgeKnower(Base):
    """Links a fact to whoever (player / NPC / simulated player) knows it.
    Absence of a row means the knower does NOT know the fact — this is how
    NPCs are prevented from using information they were never told."""

    __tablename__ = "knowledge_knowers"
    __table_args__ = (
        UniqueConstraint(
            "fact_id",
            "knower_type",
            "knower_id",
            name="uq_knowledge_knower_fact_identity",
        ),
        Index("ix_knowledge_knower_identity", "knower_type", "knower_id", "fact_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("know"))
    fact_id: Mapped[str] = mapped_column(ForeignKey("knowledge_facts.id"), nullable=False)
    knower_type: Mapped[str] = mapped_column(String, nullable=False)
    knower_id: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, default="system")
    certainty: Mapped[str] = mapped_column(String, default="CONFIRMED")
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
