from sqlalchemy import ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class GenesisHydroGeometryPlan(Base):
    __tablename__ = "genesis_hydro_geometry_plans"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_terrain_plans.campaign_id"),
        ForeignKey("genesis_hydrology_refinements.campaign_id"), primary_key=True)
    geometry_version: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisHydroGeometryEvidence(Base):
    __tablename__ = "genesis_hydro_geometry_evidence"
    __table_args__ = (UniqueConstraint("campaign_id", "preparation_key", name="uq_g1_preparation"),)
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_hydro_geometry_plans.campaign_id"), primary_key=True)
    request_id: Mapped[str] = mapped_column(String, primary_key=True)
    preparation_key: Mapped[str | None] = mapped_column(String, nullable=True)
    baseline_checksum: Mapped[str] = mapped_column(String, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False, deferred=True)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
