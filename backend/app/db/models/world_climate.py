from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenesisClimatePlan(Base):
    __tablename__ = "genesis_climate_plans"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_hydrology_plans.campaign_id"), primary_key=True)
    climate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_signature: Mapped[str] = mapped_column(String, nullable=False)
    source_checksum: Mapped[str] = mapped_column(String, nullable=False)
    hydrology_signature: Mapped[str] = mapped_column(String, nullable=False)
    hydrology_checksum: Mapped[str] = mapped_column(String, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_checksum: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False, deferred=True)


class GenesisClimateSector(Base):
    __tablename__ = "genesis_climate_sectors"
    __table_args__ = (CheckConstraint("face >= 0 AND face < 6 AND x >= 0 AND y >= 0", name="ck_climate_sector_address"),)
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_climate_plans.campaign_id"), primary_key=True)
    face: Mapped[int] = mapped_column(Integer, primary_key=True)
    x: Mapped[int] = mapped_column(Integer, primary_key=True)
    y: Mapped[int] = mapped_column(Integer, primary_key=True)
    baseline_checksum: Mapped[str] = mapped_column(String, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
