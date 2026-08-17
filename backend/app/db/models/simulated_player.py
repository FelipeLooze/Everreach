from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import SimulatedPlayerArchetype, SimulatedPlayerStatus
from app.core.ids import generate_id
from app.db.base import Base


class SimulatedPlayer(Base):
    """A rule-driven stand-in for another player sharing the world. Not an NPC:
    it has its own goals and keeps existing/acting while the protagonist is elsewhere."""

    __tablename__ = "simulated_players"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("simp"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=0)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)

    archetype: Mapped[str] = mapped_column(String, default=SimulatedPlayerArchetype.EXPLORER)
    goal: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default=SimulatedPlayerStatus.ACTIVE)
