from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    OrganizationFormality,
    OrganizationMembershipStatus,
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
    formality: Mapped[str] = mapped_column(
        String, default=OrganizationFormality.INFORMAL, nullable=False
    )
    founding_group_id: Mapped[str | None] = mapped_column(ForeignKey("groups.id"), nullable=True)


class OrganizationRole(Base):
    """Phase 13F — roles belong to ONE organization. There is
    deliberately no shared global rank list (Recruit/Member/Officer/
    Leader) reused across every organization — a Hunter Guild's
    "Guildmaster" and a Church's "High Priest" are unrelated rows, each
    scoped to their own organization_id, with their own title and
    hierarchy position."""

    __tablename__ = "organization_roles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("orole"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    rank_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    permissions_json: Mapped[str] = mapped_column(String, default="[]", nullable=False)


class OrganizationMember(Base):
    """One row per membership stint (not per member) — an expulsion
    followed by a later rejoin are two distinct historical facts, both
    preserved, rather than one row silently overwritten."""

    __tablename__ = "organization_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("omember"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    member_type: Mapped[str] = mapped_column(String, nullable=False)
    member_id: Mapped[str] = mapped_column(String, nullable=False)
    role_id: Mapped[str | None] = mapped_column(ForeignKey("organization_roles.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String, default=OrganizationMembershipStatus.ACTIVE, nullable=False
    )
    joined_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    left_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
