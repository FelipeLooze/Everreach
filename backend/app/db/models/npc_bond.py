from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import generate_id
from app.db.base import Base


class NPCBond(Base):
    """A tie between two NPCs of one village (app.game.npcs.bonds): family,
    a master and apprentice, friends or rivals. Everyone in the village
    knows these; the narrator uses them instead of inventing relatives."""

    __tablename__ = "npc_bonds"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("bond"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    settlement_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    # For PARENT and MASTER, first is the parent/master; the rest are mutual.
    first_npc_id: Mapped[str] = mapped_column(ForeignKey("npcs.id"), nullable=False)
    second_npc_id: Mapped[str] = mapped_column(ForeignKey("npcs.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    # Why rivals quarrel, in Portuguese; empty for the others.
    note: Mapped[str] = mapped_column(String, default="", nullable=False)
