from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    OrganizationOrigin,
    OrganizationStatus,
    OrganizationType,
    OrganizationVisibility,
)
from app.core.ids import generate_id
from app.db.base import Base


class Organization(Base):
    """Phase 13C — a persistent social entity, independent of the
    protagonist. GROUP != ORGANIZATION: unlike Group (Phase 13A, smaller
    and often temporary, no infrastructure required), an Organization is
    the persistent kind — but foundation-only here, with no members yet
    (that's Phase 13F's MEMBERSHIP RECORD) and no roles, reputation,
    relationships, goals, or resources (13F-13J)."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("org"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    organization_type: Mapped[str] = mapped_column(String, default=OrganizationType.OTHER, nullable=False)
    description: Mapped[str] = mapped_column(String, default="", nullable=False)
    status: Mapped[str] = mapped_column(String, default=OrganizationStatus.ACTIVE, nullable=False)
    visibility: Mapped[str] = mapped_column(
        String, default=OrganizationVisibility.PUBLIC, nullable=False
    )
    headquarters_location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    founder_type: Mapped[str | None] = mapped_column(String, nullable=True)
    founder_id: Mapped[str | None] = mapped_column(String, nullable=True)
    founded_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[str] = mapped_column(String, default=OrganizationOrigin.NATIVE, nullable=False)
    transported_people_stance: Mapped[str | None] = mapped_column(String, nullable=True)
