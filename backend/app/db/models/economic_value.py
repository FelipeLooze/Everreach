from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class EconomicCanonValue(Base):
    """One lazily materialized canonical base value.

    ``canonical_key`` is the concurrency/idempotency boundary.  Commodity
    items normally key by ItemDefinition, unique objects by ItemInstance,
    and services by location plus service key.  Current transaction prices
    remain derived by the Phase 14 pricing services.
    """

    __tablename__ = "economic_canon_values"
    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_economic_canon_value_key"),
        CheckConstraint(
            "classification IN ('MARKET_PRICE', 'NOT_FOR_SALE', "
            "'NO_ESTABLISHED_MARKET', 'NEGOTIATED_ONLY', 'UNIQUE_OR_PRICELESS')",
            name="ck_economic_value_classification",
        ),
        CheckConstraint(
            "provenance IN ('SEEDED', 'DETERMINISTIC', 'LLM_PROPOSED', "
            "'CRAFT_DERIVED', 'WORLD_EVENT', 'CANON_OVERRIDE')",
            name="ck_economic_value_provenance",
        ),
        CheckConstraint(
            "(classification = 'MARKET_PRICE' AND base_price_bronze IS NOT NULL "
            "AND base_price_bronze > 0) OR "
            "(classification <> 'MARKET_PRICE' AND base_price_bronze IS NULL)",
            name="ck_economic_value_price_shape",
        ),
        Index("ix_economic_value_campaign_subject", "campaign_id", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("econvalue")
    )
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String, nullable=False)
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    provider_type: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String, nullable=True)
    classification: Mapped[str] = mapped_column(String, nullable=False)
    base_price_bronze: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str] = mapped_column(String, default="", nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
