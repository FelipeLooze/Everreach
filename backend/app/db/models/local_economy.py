from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import SettlementWealthBand
from app.core.ids import generate_id
from app.db.base import Base


class LocationEconomy(Base):
    """Phase 14I — one settlement's broad economic character. Reuses the
    existing Location model (Phase 4) rather than inventing a new
    "settlement" entity; not every Location needs a row here (absence
    reads as MODEST, an unremarkable default — see
    app.game.economy.local_economy.get_settlement_wealth)."""

    __tablename__ = "location_economies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("lecon"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False, unique=True)
    wealth_band: Mapped[str] = mapped_column(String, default=SettlementWealthBand.MODEST, nullable=False)
