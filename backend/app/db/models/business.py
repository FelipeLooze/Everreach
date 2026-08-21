from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import BusinessStatus, BusinessType
from app.core.ids import generate_id
from app.db.base import Base


class Business(Base):
    """Phase 14J — ownership structure, separate from Phase 14G's Shop
    (retail buying/selling behavior). OWNER != OPERATOR: owner_type is
    EconomicActorType (an Organization may own a business, Phase 14L);
    operator is who actually runs it day to day — CHARACTER/NPC, since
    only those can hold a Shop's inventory (Phase 10's constraint) — and
    is optional: a business the owner personally runs has no separate
    operator record needed beyond owner==operator by convention."""

    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("biz"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    business_type: Mapped[str] = mapped_column(String, default=BusinessType.OTHER, nullable=False)
    owner_type: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    operator_type: Mapped[str | None] = mapped_column(String, nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default=BusinessStatus.ACTIVE, nullable=False)
    founded_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    # Phase 14K — the business's own funds, separate from its owner's
    # personal/organizational money (see app.game.economy.actors).
    till_bronze: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
