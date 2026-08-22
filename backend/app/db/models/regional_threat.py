from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ThreatIntensity, ThreatType
from app.core.ids import generate_id
from app.db.base import Base


class RegionalThreat(Base):
    """Phase 15L — a population/habitat abstraction (never an individual
    creature instance) that gives world simulation and future world
    events something real to reference (e.g. "boars leave the forest,
    crops get damaged" — spec's own worked example). Persists whether or
    not the protagonist has ever encountered it."""

    __tablename__ = "regional_threats"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("threat"))
    subregion_id: Mapped[str] = mapped_column(ForeignKey("subregions.id"), nullable=False)
    threat_type: Mapped[str] = mapped_column(String, default=ThreatType.WOLVES)
    intensity: Mapped[str] = mapped_column(String, default=ThreatIntensity.LOW)
    description: Mapped[str] = mapped_column(String, default="")
