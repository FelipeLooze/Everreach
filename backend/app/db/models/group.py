from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import GroupInviteStatus, GroupStatus, GroupType
from app.core.ids import generate_id
from app.db.base import Base


class Group(Base):
    """Phase 13A — smaller, often temporary, agency-driven social grouping.
    Deliberately NOT the same thing as SimulatedPlayerGroup (Phase 7,
    app/db/models/simulated_player_group.py) — that one is an internal
    world-simulation mechanism for moving background simulated players in
    sync and has no concept of consent; this one represents a real social
    decision (see app.game.groups.service) and may include the
    protagonist and NPCs, not just simulated players. Also not the same
    thing as an Organization (Phase 13C+) — a Group is not persistent
    infrastructure."""

    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("group"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    group_type: Mapped[str] = mapped_column(String, default=GroupType.OTHER, nullable=False)
    purpose: Mapped[str] = mapped_column(String, default="", nullable=False)
    status: Mapped[str] = mapped_column(String, default=GroupStatus.ACTIVE, nullable=False)
    leader_type: Mapped[str | None] = mapped_column(String, nullable=True)
    leader_id: Mapped[str | None] = mapped_column(String, nullable=True)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "member_type", "member_id", name="uq_group_member"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("gmember"))
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"), nullable=False)
    member_type: Mapped[str] = mapped_column(String, nullable=False)
    member_id: Mapped[str] = mapped_column(String, nullable=False)
    joined_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    left_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GroupInvite(Base):
    """Phase 13B — a pending social proposal, never assumed accepted. See
    app.game.groups.service.accept_invite/decline_invite."""

    __tablename__ = "group_invites"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("ginvite"))
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id"), nullable=False)
    inviter_type: Mapped[str] = mapped_column(String, nullable=False)
    inviter_id: Mapped[str] = mapped_column(String, nullable=False)
    invited_type: Mapped[str] = mapped_column(String, nullable=False)
    invited_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default=GroupInviteStatus.PENDING, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
