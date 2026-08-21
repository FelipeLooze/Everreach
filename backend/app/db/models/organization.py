from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    OrganizationFormality,
    OrganizationGoalStatus,
    OrganizationMembershipStatus,
    OrganizationNeedStatus,
    OrganizationOrigin,
    OrganizationRelationStatus,
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
    treasury: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


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


class OrganizationRelation(Base):
    """Phase 13H — one row per relationship FACT, not per organization
    pair. Multiple rows of different relation_type may coexist and be
    ACTIVE at once between the same two organizations (e.g.
    TRADE_PARTNER and COMPETITOR simultaneously) — nothing here collapses
    diplomacy into a single exclusive value or a bare number. Ended
    relations are never deleted, preserving history."""

    __tablename__ = "organization_relations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("orel"))
    organization_a_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    organization_b_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String, default=OrganizationRelationStatus.ACTIVE, nullable=False
    )
    established_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    ended_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OrganizationGoal(Base):
    """Phase 13I — GOAL != NEED. A goal is the qualitative "why"
    (protect the trade route); a need (below) is the concrete "what it
    takes" (more hunters, arrows). Free-text description — goals are too
    varied for a fixed enum to capture meaningfully."""

    __tablename__ = "organization_goals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("ogoal"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default=OrganizationGoalStatus.ACTIVE, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class OrganizationNeed(Base):
    """A concrete resource/capability gap, optionally in service of a
    Goal. This is the source of real-world activity (Phase 13M routes
    needs toward Notices/jobs) — not something the player triggers by
    opening a board."""

    __tablename__ = "organization_needs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("oneed"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    goal_id: Mapped[str | None] = mapped_column(ForeignKey("organization_goals.id"), nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default=OrganizationNeedStatus.OPEN, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class OrganizationAsset(Base):
    """Phase 13J — links an existing ItemInstance (Phase 10) to the
    organization that beneficially owns it, WITHOUT touching
    ItemInstance.owner_type/location_type — both are hard-constrained at
    the database level to CHARACTER/NPC/NONE and cannot represent
    organizational ownership; widening that constraint would be a
    Phase-10-level schema change, out of scope here (flagged, not
    silently worked around). The item's physical existence, quality,
    durability, and current physical placement/container remain entirely
    governed by the existing Item system; this only answers "which
    organization is the beneficial owner" — a guildmaster personally
    carrying a guild-owned sword is a completely different fact from the
    guild owning it, and both can be true at once."""

    __tablename__ = "organization_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("oasset"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    item_instance_id: Mapped[str] = mapped_column(
        ForeignKey("item_instances.id"), nullable=False, unique=True
    )
    acquired_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class OrganizationAction(Base):
    """Phase 13K — an append-only record that the organization, as an
    entity, did something. This is the "clean hook" the spec asks for
    instead of a giant hardcoded per-action condition chain: any
    authoritative function may write one; action_type draws from
    OrganizationActionType's small, extensible vocabulary (OTHER covers
    anything validated but not yet mechanized). Authority always comes
    from the backend — see app.game.organizations.actions; the Narrator
    only ever describes a row that already exists here."""

    __tablename__ = "organization_actions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("oaction"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    actor_type: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
