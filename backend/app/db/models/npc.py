from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
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
    # Simplification Pass S1.2 — the NPC's home/base location above never
    # changes after seeding; this is the SEPARATE, optional service
    # location (e.g. the inn, the forge) this NPC is normally found at
    # while WORKING. Nullable and additive: an NPC without one (every
    # existing save, and any NPC whose role has no obvious workplace)
    # behaves exactly as before — see npcs_at_location's effective-location
    # resolution in app.game.npcs.service.
    workplace_location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    personality: Mapped[str] = mapped_column(String, default="")
    backstory: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="villager")
    # Structured personality (app.game.npcs.profile); filled lazily for any
    # NPC created without one.
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_json: Mapped[str] = mapped_column(String, default="{}", server_default="{}", nullable=False)
    # Hour-by-hour routine of a resident (app.game.npcs.residents); empty for
    # NPCs that follow activity_for_role. visiting_location_id is the
    # building they are in right now when it is neither their base nor
    # their workplace (the inn at lunch).
    routine_json: Mapped[str] = mapped_column(String, default="[]", server_default="[]", nullable=False)
    visiting_location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    activity: Mapped[str] = mapped_column(
        String,
        default=NPCActivity.AVAILABLE,
        nullable=False,
    )

    alive: Mapped[bool] = mapped_column(Boolean, default=True)
    incapacitated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 0-100. Persistent, never decays on its own. Attacking an NPC sets this
    # to the maximum; some NPCs may also start hostile by design (bandits,
    # dangerous creatures). See app/game/combat/hostility.py.
    hostility: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hp_current: Mapped[float] = mapped_column(Float, default=10, nullable=False)
    hp_max: Mapped[float] = mapped_column(Float, default=10, nullable=False)
    mana_current: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    mana_max: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    stamina_current: Mapped[float] = mapped_column(Float, default=10, nullable=False)
    stamina_max: Mapped[float] = mapped_column(Float, default=10, nullable=False)
