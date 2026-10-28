from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenesisHydrologyRefinement(Base):
    __tablename__ = "genesis_hydrology_refinements"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_hydrology_plans.campaign_id"), primary_key=True)
    refinement_version: Mapped[int] = mapped_column(Integer, nullable=False)
    hydrology_signature: Mapped[str] = mapped_column(String, nullable=False)
    hydrology_checksum: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisHydrologyRegion(Base):
    __tablename__ = "genesis_hydrology_regions"
    __table_args__ = (CheckConstraint("node >= 0 AND node < 6144", name="ck_hydrology_region_node"),)
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_hydrology_refinements.campaign_id"), primary_key=True)
    node: Mapped[int] = mapped_column(Integer, primary_key=True)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    baseline_checksum: Mapped[str] = mapped_column(String, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
