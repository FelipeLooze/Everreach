from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class GenesisSphereSector(Base):
    __tablename__ = "genesis_sphere_sectors"
    __table_args__ = (CheckConstraint("face >= 0 AND face < 6 AND x >= 0 AND y >= 0",
                                     name="ck_sphere_sector_address"),)

    campaign_id: Mapped[str] = mapped_column(ForeignKey("genesis_worlds.campaign_id"), primary_key=True)
    face: Mapped[int] = mapped_column(Integer, primary_key=True)
    x: Mapped[int] = mapped_column(Integer, primary_key=True)
    y: Mapped[int] = mapped_column(Integer, primary_key=True)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class LocationSpatialAnchor(Base):
    __tablename__ = "location_spatial_anchors"

    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("genesis_worlds.campaign_id"), index=True, nullable=False)
    point: Mapped[list] = mapped_column(JSON, nullable=False)


class EntitySpatialCoverage(Base):
    """Sparse quadtree cells, without expansion to all covered sectors."""

    __tablename__ = "entity_spatial_coverages"
    __table_args__ = (
        CheckConstraint("(region_id IS NOT NULL AND subregion_id IS NULL) OR "
                        "(region_id IS NULL AND subregion_id IS NOT NULL)", name="ck_coverage_owner"),
        CheckConstraint("face >= 0 AND face < 6 AND level >= 0 AND level <= 24 AND "
                        "x >= 0 AND y >= 0 AND x < (1 << level) AND y < (1 << level)",
                        name="ck_coverage_address"),
        UniqueConstraint("region_id", "face", "level", "x", "y", name="uq_region_coverage_cell"),
        UniqueConstraint("subregion_id", "face", "level", "x", "y", name="uq_subregion_coverage_cell"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("coverage"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("genesis_worlds.campaign_id"), index=True, nullable=False)
    region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    subregion_id: Mapped[str | None] = mapped_column(ForeignKey("subregions.id"), nullable=True)
    face: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
