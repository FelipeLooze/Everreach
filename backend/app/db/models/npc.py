from sqlalchemy import Boolean, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base
from app.core.enums import NPCActivity

class NPC(Base):
    """NPCs believe they were born in this world — see ai/prompts/narrator_system.txt.
    They never know they are inside a game."""

    __tablename__ = "npcs"
    __table_args__ = (
        Index(
            "ix_npcs_campaign_location_alive",
            "campaign_id",
            "location_id",
            "alive",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("npc"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), nullable=False)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    personality: Mapped[str] = mapped_column(String, default="")
    backstory: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="villager")

    activity: Mapped[str] = mapped_column(
        String,
        default=NPCActivity.AVAILABLE,
        nullable=False,
    )

    alive: Mapped[bool] = mapped_column(Boolean, default=True)
    hp_current: Mapped[float] = mapped_column(Float, default=10, nullable=False)
    hp_max: Mapped[float] = mapped_column(Float, default=10, nullable=False)
