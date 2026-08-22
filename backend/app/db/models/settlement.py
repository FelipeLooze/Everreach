from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import SettlementType
from app.core.ids import generate_id
from app.db.base import Base


class Settlement(Base):
    """Phase 15F — Settlement Network. A thin overlay on an existing
    Location (never a parallel geography system): every settlement IS a
    Location (with x/y, connections, features, discovery status already
    working), this table only adds settlement-specific identity.
    Reuses the Location itself as the anchor Phase 14's local economy
    (app.game.economy.local_economy, keyed by location_id) already
    expects, so wiring Phase 14K/14G shops/wealth to a generated
    settlement needs no new plumbing."""

    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("settlement"))
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False, unique=True)
    settlement_type: Mapped[str] = mapped_column(String, default=SettlementType.VILLAGE)
    profile: Mapped[str] = mapped_column(String, default="")
    population_tier: Mapped[int] = mapped_column(Integer, default=1)
