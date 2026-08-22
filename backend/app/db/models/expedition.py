from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ExpeditionStatus
from app.core.ids import generate_id
from app.db.base import Base


class Expedition(Base):
    """
    Phase 17I — a planned journey focused on exploration, discovery, or
    reaching difficult territory. A thin overlay on Group (Phase 13A,
    which already has GroupType.EXPEDITION), the same pattern Settlement
    uses over Location and Map uses over ItemInstance: Group already
    owns participants/leader/agency (an invite, never assumed
    accepted); this table only adds what's specific to being an
    expedition — where it's headed (optional: some expeditions survey
    unknown wilderness with no fixed destination) and how it resolved.
    """

    __tablename__ = "expeditions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("expedition"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"), nullable=False, unique=True)

    purpose: Mapped[str] = mapped_column(String, default="")
    target_subject_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(String, nullable=True)

    origin_location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)

    status: Mapped[str] = mapped_column(String, nullable=False, default=ExpeditionStatus.PLANNED)

    started_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
