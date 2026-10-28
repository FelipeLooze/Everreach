from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenesisFormationCandidate(Base):
    """Deterministic WGS1-v2 placement decision, including rejected sites."""
    __tablename__ = "genesis_formation_candidates"
    __table_args__ = (
        UniqueConstraint("campaign_id", "stable_key", name="uq_formation_candidate_key"),
        Index("ix_formation_candidate_campaign", "campaign_id"),
        CheckConstraint("status IN ('accepted', 'rejected', 'materialized')", name="ck_formation_candidate_status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    stable_key: Mapped[str] = mapped_column(String, nullable=False)
    archetype_id: Mapped[str] = mapped_column(String, nullable=False)
    generator_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisNaturalFormation(Base):
    """Persisted local formation instance, separate from regional authorities."""
    __tablename__ = "genesis_natural_formations"
    __table_args__ = (UniqueConstraint("campaign_id", "stable_key", name="uq_natural_formation_key"),
                      Index("ix_natural_formation_campaign", "campaign_id"))

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False, unique=True)
    stable_key: Mapped[str] = mapped_column(String, nullable=False)
    archetype_id: Mapped[str] = mapped_column(String, nullable=False)
    generator_version: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisFormationCoverageCell(Base):
    """Versioned sparse footprint cell for a persisted formation instance.

    This describes physical coverage only; it is not a Location or a travel
    edge. Access continues to be represented by the existing Location graph.
    """
    __tablename__ = "genesis_formation_coverage_cells"
    __table_args__ = (
        UniqueConstraint("campaign_id", "formation_id", "face", "level", "x", "y",
                         name="uq_formation_coverage_cell"),
        Index("ix_formation_coverage_address", "campaign_id", "face", "level", "x", "y"),
        CheckConstraint("face >= 0 AND face < 6 AND level >= 0 AND level <= 24 AND x >= 0 AND y >= 0",
                        name="ck_formation_coverage_cell_address"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    formation_id: Mapped[str] = mapped_column(ForeignKey("genesis_natural_formations.id"), nullable=False)
    access_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    face: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_version: Mapped[str] = mapped_column(String, nullable=False)
    contract_checksum: Mapped[str] = mapped_column(String, nullable=False)


class GenesisLocalWaterBody(Base):
    """A formation-owned finite pool. Never included in W1/W2/P1 ledgers."""
    __tablename__ = "genesis_local_water_bodies"
    __table_args__ = (CheckConstraint("capacity_litres > 0 AND stored_litres >= 0 AND stored_litres <= capacity_litres",
                                      name="ck_local_water_bounds"),)
    formation_id: Mapped[str] = mapped_column(ForeignKey("genesis_natural_formations.id"), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    capacity_litres: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_litres: Mapped[int] = mapped_column(Integer, nullable=False)
    source_origin: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
