from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    CombatIncapacitationStatus,
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
    autonomous_decisions: Mapped[list["CombatAutonomousDecision"]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="CombatAutonomousDecision.created_world_minute, CombatAutonomousDecision.id",
    )
    conditions: Mapped[list["CombatCondition"]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="CombatCondition.id",
    )
    incapacitations: Mapped[list["CombatIncapacitation"]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="CombatIncapacitation.created_world_minute",
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
        CheckConstraint(
            "weapon_instance_id IS NULL OR physical_damage_profile IS NOT NULL",
            name="ck_combat_action_weapon_mechanics",
        ),
        CheckConstraint(
            "physical_damage_profile IS NULL OR "
            "physical_damage_profile IN ('SLASH', 'PIERCE', 'BLUNT')",
            name="ck_combat_action_physical_damage_profile",
        ),
        CheckConstraint(
            "(damage_type = 'PHYSICAL' AND physical_damage_profile IS NOT NULL "
            "AND target_body_area IS NOT NULL) OR "
            "(damage_type <> 'PHYSICAL' AND physical_damage_profile IS NULL "
            "AND target_body_area IS NULL)",
            name="ck_combat_action_physical_semantics",
        ),
        CheckConstraint(
            "target_body_area IS NULL OR target_body_area IN "
            "('HEAD', 'TORSO', 'ARMS', 'HANDS', 'LEGS', 'FEET')",
            name="ck_combat_action_target_body_area",
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
    weapon_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("item_instances.id"), nullable=True
    )
    physical_damage_profile: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    target_body_area: Mapped[str | None] = mapped_column(String, nullable=True)
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
    incapacitating: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    base_damage_dice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_die_sides: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_attribute: Mapped[str | None] = mapped_column(String, nullable=True)
    damage_type: Mapped[str] = mapped_column(String, default="PHYSICAL", nullable=False)
    damage_before_mitigation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    armor_mitigation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resistance_mitigation: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


class CombatAutonomousDecision(Base):
    """Auditable backend choice made for one non-protagonist combat turn."""

    __tablename__ = "combat_autonomous_decisions"
    __table_args__ = (
        UniqueConstraint("turn_id", name="uq_combat_autonomous_decision_turn"),
        UniqueConstraint(
            "encounter_id",
            "decision_key",
            name="uq_combat_autonomous_decision_key",
        ),
        Index(
            "ix_combat_autonomous_decision_encounter_time",
            "encounter_id",
            "created_world_minute",
        ),
    )

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_id("combat_decision"),
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
    combat_action_id: Mapped[str | None] = mapped_column(
        ForeignKey("combat_actions.id"), nullable=True
    )
    tactical_action_id: Mapped[str | None] = mapped_column(
        ForeignKey("combat_tactical_actions.id"), nullable=True
    )
    decision_key: Mapped[str] = mapped_column(String, nullable=False)
    decision_kind: Mapped[str] = mapped_column(String, nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    risk_tolerance: Mapped[str] = mapped_column(String, nullable=False)
    hp_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    stamina_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)

    encounter: Mapped["CombatEncounter"] = relationship(
        back_populates="autonomous_decisions"
    )
    turn: Mapped["CombatTurn"] = relationship()
    actor_participant: Mapped["CombatParticipant"] = relationship(
        foreign_keys=[actor_participant_id]
    )
    target_participant: Mapped["CombatParticipant | None"] = relationship(
        foreign_keys=[target_participant_id]
    )
    combat_action: Mapped["CombatAction | None"] = relationship()
    tactical_action: Mapped["CombatTacticalAction | None"] = relationship()


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


class CombatIncapacitation(Base):
    """Persistent critical state created when a non-devastating hit reduces HP to zero."""

    __tablename__ = "combat_incapacitations"
    __table_args__ = (
        UniqueConstraint("encounter_id", "participant_id", name="uq_combat_incapacitation_participant"),
        UniqueConstraint("source_action_id", name="uq_combat_incapacitation_source_action"),
        Index("ix_combat_incapacitation_actor_status", "actor_type", "actor_id", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("critical"))
    encounter_id: Mapped[str] = mapped_column(ForeignKey("combat_encounters.id"), nullable=False)
    participant_id: Mapped[str] = mapped_column(ForeignKey("combat_participants.id"), nullable=False)
    source_action_id: Mapped[str] = mapped_column(ForeignKey("combat_actions.id"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default=CombatIncapacitationStatus.CRITICAL.value, nullable=False)
    stabilization_successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    death_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_reason: Mapped[str] = mapped_column(String, default="", nullable=False)
    recovery_key: Mapped[str | None] = mapped_column(String, nullable=True)

    encounter: Mapped["CombatEncounter"] = relationship(back_populates="incapacitations")
    participant: Mapped["CombatParticipant"] = relationship()
    source_action: Mapped["CombatAction"] = relationship()
    checks: Mapped[list["CombatCriticalCheck"]] = relationship(
        back_populates="incapacitation", cascade="all, delete-orphan", order_by="CombatCriticalCheck.id"
    )


class CombatCriticalCheck(Base):
    """Idempotent death/stabilization check for a critical actor."""

    __tablename__ = "combat_critical_checks"
    __table_args__ = (
        UniqueConstraint("incapacitation_id", "check_key", name="uq_combat_critical_check_key"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("critical_check"))
    incapacitation_id: Mapped[str] = mapped_column(ForeignKey("combat_incapacitations.id"), nullable=False)
    check_key: Mapped[str] = mapped_column(String, nullable=False)
    roll: Mapped[int] = mapped_column(Integer, nullable=False)
    modifier: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    dc: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    successes_before: Mapped[int] = mapped_column(Integer, nullable=False)
    successes_after: Mapped[int] = mapped_column(Integer, nullable=False)
    failures_before: Mapped[int] = mapped_column(Integer, nullable=False)
    failures_after: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    created_world_minute: Mapped[int] = mapped_column(Integer, nullable=False)

    incapacitation: Mapped["CombatIncapacitation"] = relationship(back_populates="checks")
