from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class GenesisTerrainPlan(Base):
    __tablename__ = "genesis_terrain_plans"
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_worlds.campaign_id"), primary_key=True)
    terrain_version: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str] = mapped_column(String, nullable=False)
    source_checksum: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)


class GenesisTerrainTile(Base):
    __tablename__ = "genesis_terrain_tiles"
    __table_args__ = (CheckConstraint("face >= 0 AND face < 6 AND level >= 0 AND level <= 46 AND x >= 0 AND y >= 0",
                                    name="ck_terrain_tile_address"),)
    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("genesis_terrain_plans.campaign_id"), primary_key=True)
    face: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[int] = mapped_column(Integer, primary_key=True)
    x: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    y: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    baseline_checksum: Mapped[str] = mapped_column(String, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False, deferred=True)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
