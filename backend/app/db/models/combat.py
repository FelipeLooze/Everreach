from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    CombatAwareness,
    CombatEncounterStatus,
    CombatRangeBand,
    CombatTurnStatus,
)
from app.core.ids import generate_id
from app.db.base import Base


class CombatEncounter(Base):
    """Persisted authoritative boundary for one physical confrontation."""

    __tablename__ = "combat_encounters"
    __table_args__ = (
        Index(
            "ix_combat_encounter_campaign_status",
            "campaign_id",
            "status",
        ),
        Index(
            "ix_combat_encounter_location_status",
            "location_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("combat"),
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
    )
    location_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String,
        default=CombatEncounterStatus.ACTIVE.value,
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_turn_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    ended_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_reason: Mapped[str] = mapped_column(String, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    participants: Mapped[list["CombatParticipant"]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="CombatParticipant.id",
    )
    turns: Mapped[list["CombatTurn"]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="CombatTurn.round_number, CombatTurn.turn_order",
    )


class CombatParticipant(Base):
    """A concrete living actor participating on one side of an encounter."""

    __tablename__ = "combat_participants"
    __table_args__ = (
        UniqueConstraint(
            "encounter_id",
            "actor_type",
            "actor_id",
            name="uq_combat_participant_actor",
        ),
        Index(
            "ix_combat_participant_actor_active",
            "actor_type",
            "actor_id",
            "active",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("combatant"),
    )
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("combat_encounters.id"),
        nullable=False,
    )
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    side_key: Mapped[str] = mapped_column(String, nullable=False)
    range_band: Mapped[str] = mapped_column(
        String,
        default=CombatRangeBand.NEAR.value,
        nullable=False,
    )
    awareness: Mapped[str] = mapped_column(
        String,
        default=CombatAwareness.AWARE.value,
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    left_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    left_reason: Mapped[str] = mapped_column(String, default="", nullable=False)
    initiative_roll: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initiative_modifier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initiative_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    encounter: Mapped["CombatEncounter"] = relationship(
        back_populates="participants"
    )


class CombatTurn(Base):
    """One persisted turn slot, including completed and automatically skipped turns."""

    __tablename__ = "combat_turns"
    __table_args__ = (
        UniqueConstraint(
            "encounter_id",
            "round_number",
            "turn_order",
            name="uq_combat_turn_slot",
        ),
        UniqueConstraint(
            "encounter_id",
            "completion_key",
            name="uq_combat_turn_completion_key",
        ),
        Index("ix_combat_turn_encounter_status", "encounter_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("turn"),
    )
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("combat_encounters.id"),
        nullable=False,
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("combat_participants.id"),
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        default=CombatTurnStatus.ACTIVE.value,
        nullable=False,
    )
    started_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    ended_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_key: Mapped[str | None] = mapped_column(String, nullable=True)

    encounter: Mapped["CombatEncounter"] = relationship(back_populates="turns")
    participant: Mapped["CombatParticipant"] = relationship()
