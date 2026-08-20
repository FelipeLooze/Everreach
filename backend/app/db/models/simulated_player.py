from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    SimulatedPlayerActivity,
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
    SimulatedPlayerStatus,
)
from app.core.ids import generate_id
from app.db.base import Base


class SimulatedPlayer(Base):
    """A rule-driven stand-in for another player sharing the world. Not an NPC:
    it has its own goals and keeps existing/acting while the protagonist is elsewhere."""

    __tablename__ = "simulated_players"
    __table_args__ = (
        Index(
            "ix_simulated_players_campaign_location_status",
            "campaign_id",
            "location_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("simp"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[float] = mapped_column(Float, default=0)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)

    archetype: Mapped[str] = mapped_column(String, default=SimulatedPlayerArchetype.EXPLORER)
    risk_tolerance: Mapped[str] = mapped_column(
        String,
        default="BALANCED",
        server_default="BALANCED",
        nullable=False,
    )
    goal: Mapped[str] = mapped_column(String, default="")

    personality: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    background: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    motivation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    physical_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    goal_type: Mapped[str] = mapped_column(
        String,
        default=SimulatedPlayerGoalType.NONE,
        nullable=False,
    )

    goal_subject: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    activity: Mapped[str] = mapped_column(
        String,
        default=SimulatedPlayerActivity.AVAILABLE,
        server_default=SimulatedPlayerActivity.AVAILABLE,
        nullable=False,
    )

    activity_until_world_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(String, default=SimulatedPlayerStatus.ACTIVE)
    travel_connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("location_connections.id"),
        nullable=True,
    )

    travel_destination_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"),
        nullable=True,
    )

    travel_started_world_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    travel_arrival_world_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

class SimulatedPlayerPopulation(Base):
    """
    Abstract transported population at one concrete location.

    People represented here do not yet have individual identities.
    Materialization will later consume this population and create
    persistent SimulatedPlayer rows.
    """

    __tablename__ = "simulated_player_populations"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("sppop"),
    )

    location_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id"),
        unique=True,
        nullable=False,
    )

    abstract_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )


class SimulatedPlayerSkill(Base):
    __tablename__ = "simulated_player_skills"
    __table_args__ = (
        UniqueConstraint(
            "simulated_player_id",
            "name",
            name="uq_simulated_player_skill_name",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("spskill"),
    )
    simulated_player_id: Mapped[str] = mapped_column(
        ForeignKey("simulated_players.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    mastery: Mapped[float] = mapped_column(Float, default=0, nullable=False)
