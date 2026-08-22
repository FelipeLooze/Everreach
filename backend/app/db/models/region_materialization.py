from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RegionMaterializationRequestStatus
from app.core.ids import generate_id
from app.db.base import Base


class RegionMaterializationRequest(Base):
    """
    Phase 16A — an authoritative record that a neighboring Region needs to
    exist. Any system may create one (see RegionMaterializationRequestSource
    in app.core.enums) — the protagonist is not a privileged trigger.

    A request does not generate a Region by itself; it only records that
    one is needed, by whom, and why, so a later subphase (16I+) can act on
    it. At most one PENDING request exists per (campaign, source_region) at
    a time — see app.game.world.region_materialization's dedup contract.
    """

    __tablename__ = "region_materialization_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("regreq"))

    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    source_region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), nullable=False)

    requested_by_type: Mapped[str] = mapped_column(String, nullable=False)
    requested_by_id: Mapped[str] = mapped_column(String, default="")
    reason: Mapped[str] = mapped_column(String, default="")

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=RegionMaterializationRequestStatus.PENDING,
        server_default=RegionMaterializationRequestStatus.PENDING,
    )

    requested_world_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Set once a later subphase actually generates and persists the
    # neighboring Region this request was asking for.
    fulfilled_region_id: Mapped[str | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
