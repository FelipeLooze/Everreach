from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DangerLevel, PopulationDensity, SubregionBiome
from app.core.ids import generate_id
from app.db.base import Base


class Subregion(Base):
    """Phase 15C/15D — one of many meaningful subdivisions of a massive
    Region. A Region may be near-continental in scale; Subregion is how
    that space is organized into distinct territories, each with its own
    geography/danger/population/culture/economy character — deliberately
    not interchangeable (Phase 15D spec)."""

    __tablename__ = "subregions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("subregion"))
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    biome: Mapped[str] = mapped_column(String, default=SubregionBiome.PLAINS)
    danger_level: Mapped[str] = mapped_column(String, default=DangerLevel.LOW)
    population_density: Mapped[str] = mapped_column(String, default=PopulationDensity.MODERATE)
    culture_summary: Mapped[str] = mapped_column(String, default="")
    economy_summary: Mapped[str] = mapped_column(String, default="")
