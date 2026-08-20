from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import SimulatedPlayerGroupStatus
from app.core.ids import generate_id
from app.db.base import Base


class SimulatedPlayerGroup(Base):
    __tablename__ = "simulated_player_groups"
    __table_args__ = (
        Index("ix_simulated_player_group_campaign_status", "campaign_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("spgroup")
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False
    )
    leader_id: Mapped[str] = mapped_column(
        ForeignKey("simulated_players.id"), nullable=False
    )
    location_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id"), nullable=False
    )
    goal: Mapped[str] = mapped_column(String, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        default=SimulatedPlayerGroupStatus.ACTIVE.value,
        server_default=SimulatedPlayerGroupStatus.ACTIVE.value,
        nullable=False,
    )
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class SimulatedPlayerGroupMember(Base):
    __tablename__ = "simulated_player_group_members"
    __table_args__ = (
        UniqueConstraint(
            "group_id",
            "simulated_player_id",
            name="uq_simulated_player_group_member",
        ),
        Index(
            "ix_simulated_player_active_group_membership",
            "simulated_player_id",
            "active",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: generate_id("spmember")
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("simulated_player_groups.id"), nullable=False
    )
    simulated_player_id: Mapped[str] = mapped_column(
        ForeignKey("simulated_players.id"), nullable=False
    )
    joined_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    left_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
