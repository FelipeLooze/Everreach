from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    CombatAwareness,
    CombatActionOutcome,
    CombatConditionType,
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
    actions: Mapped[list["CombatAction"]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="CombatAction.created_world_minute, CombatAction.id",
    )
    tactical_actions: Mapped[list["CombatTacticalAction"]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="CombatTacticalAction.created_world_minute, CombatTacticalAction.id",
    )
    conditions: Mapped[list["CombatCondition"]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="CombatCondition.id",
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
    conditions: Mapped[list["CombatCondition"]] = relationship(
        back_populates="participant",
        order_by="CombatCondition.id",
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


class CombatAction(Base):
    """Persisted mechanical result of the single attack resolved for one turn."""

    __tablename__ = "combat_actions"
    __table_args__ = (
        UniqueConstraint("turn_id", name="uq_combat_action_turn"),
        UniqueConstraint(
            "encounter_id",
            "action_key",
            name="uq_combat_action_key",
        ),
        Index("ix_combat_action_encounter_time", "encounter_id", "created_world_minute"),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("combat_action"),
    )
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("combat_encounters.id"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(ForeignKey("combat_turns.id"), nullable=False)
    actor_participant_id: Mapped[str] = mapped_column(
        ForeignKey("combat_participants.id"), nullable=False
    )
    target_participant_id: Mapped[str] = mapped_column(
        ForeignKey("combat_participants.id"), nullable=False
    )
    action_key: Mapped[str] = mapped_column(String, nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    technique_id: Mapped[str | None] = mapped_column(
        ForeignKey("techniques.id"), nullable=True
    )
    attack_attribute: Mapped[str] = mapped_column(String, nullable=False)
    target_range_band: Mapped[str] = mapped_column(String, nullable=False)
    attack_roll: Mapped[int] = mapped_column(Integer, nullable=False)
    attack_modifier: Mapped[int] = mapped_column(Integer, nullable=False)
    attack_total: Mapped[int] = mapped_column(Integer, nullable=False)
    defense_base: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    defense_modifier: Mapped[int] = mapped_column(Integer, nullable=False)
    defense_total: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(
        String,
        default=CombatActionOutcome.MISS.value,
        nullable=False,
    )
    damage_roll: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_dice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_modifier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_hp_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_hp_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    lethal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    base_damage_dice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_die_sides: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_attribute: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_key: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    resource_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    resource_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)

    encounter: Mapped["CombatEncounter"] = relationship(back_populates="actions")
    turn: Mapped["CombatTurn"] = relationship()
    actor_participant: Mapped["CombatParticipant"] = relationship(
        foreign_keys=[actor_participant_id]
    )
    target_participant: Mapped["CombatParticipant"] = relationship(
        foreign_keys=[target_participant_id]
    )


class CombatTacticalAction(Base):
    """Persisted non-attack action that consumes exactly one combat turn."""

    __tablename__ = "combat_tactical_actions"
    __table_args__ = (
        UniqueConstraint("turn_id", name="uq_combat_tactical_action_turn"),
        UniqueConstraint(
            "encounter_id",
            "action_key",
            name="uq_combat_tactical_action_key",
        ),
        Index(
            "ix_combat_tactical_action_encounter_time",
            "encounter_id",
            "created_world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("tactical_action"),
    )
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("combat_encounters.id"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(ForeignKey("combat_turns.id"), nullable=False)
    actor_participant_id: Mapped[str] = mapped_column(
        ForeignKey("combat_participants.id"), nullable=False
    )
    target_participant_id: Mapped[str | None] = mapped_column(
        ForeignKey("combat_participants.id"), nullable=True
    )
    action_key: Mapped[str] = mapped_column(String, nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_key: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    resource_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    resource_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_range_band: Mapped[str | None] = mapped_column(String, nullable=True)
    new_range_band: Mapped[str | None] = mapped_column(String, nullable=True)
    roll: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modifier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)

    encounter: Mapped["CombatEncounter"] = relationship(back_populates="tactical_actions")
    turn: Mapped["CombatTurn"] = relationship()
    actor_participant: Mapped["CombatParticipant"] = relationship(
        foreign_keys=[actor_participant_id]
    )
    target_participant: Mapped["CombatParticipant | None"] = relationship(
        foreign_keys=[target_participant_id]
    )


class CombatCondition(Base):
    """One idempotently applied temporary condition measured in owner turns."""

    __tablename__ = "combat_conditions"
    __table_args__ = (
        UniqueConstraint(
            "encounter_id",
            "application_key",
            name="uq_combat_condition_application",
        ),
        Index(
            "ix_combat_condition_participant_active",
            "participant_id",
            "active",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("condition"),
    )
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("combat_encounters.id"), nullable=False
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("combat_participants.id"), nullable=False
    )
    source_action_id: Mapped[str | None] = mapped_column(
        ForeignKey("combat_actions.id"), nullable=True
    )
    source_tactical_action_id: Mapped[str | None] = mapped_column(
        ForeignKey("combat_tactical_actions.id"), nullable=True
    )
    application_key: Mapped[str] = mapped_column(String, nullable=False)
    condition_type: Mapped[str] = mapped_column(
        String,
        default=CombatConditionType.WEAKENED.value,
        nullable=False,
    )
    remaining_turns: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_round: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    removed_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    removal_reason: Mapped[str] = mapped_column(String, default="", nullable=False)

    encounter: Mapped["CombatEncounter"] = relationship(back_populates="conditions")
    participant: Mapped["CombatParticipant"] = relationship(
        back_populates="conditions"
    )
    source_action: Mapped["CombatAction | None"] = relationship()
    source_tactical_action: Mapped["CombatTacticalAction | None"] = relationship()
