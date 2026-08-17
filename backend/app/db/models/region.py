from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DiscoveryStatus
from app.core.ids import generate_id
from app.db.base import Base


class Region(Base):
    """A large, self-contained part of the world. Created progressively, never all at once."""

    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("region"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")

    discovery_status: Mapped[str] = mapped_column(String, default=DiscoveryStatus.DISCOVERED)

    # Main Region Boss starts fully unknown to players (spec section 9).
    main_boss_name: Mapped[str] = mapped_column(String, default="UNKNOWN")
    main_boss_location: Mapped[str] = mapped_column(String, default="UNKNOWN")
    main_boss_requirements: Mapped[str] = mapped_column(String, default="UNKNOWN")
    main_boss_defeated: Mapped[bool] = mapped_column(default=False)
