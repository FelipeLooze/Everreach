from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    ObjectiveTriggerType,
    ObjectiveType,
    QuestParticipationType,
    QuestSource,
    QuestStatus,
)
from app.core.ids import generate_id
from app.db.base import Base


class Quest(Base):
    """A situation existing in the world, independent of any character's
    awareness or participation — see app.game.quests.service.create_quest."""

    __tablename__ = "quests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("quest"))
    region_id: Mapped[str] = mapped_column(ForeignKey("regions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default=QuestStatus.AVAILABLE, nullable=False)
    source: Mapped[str] = mapped_column(String, default=QuestSource.SELF_DISCOVERED, nullable=False)
    deadline_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("world_events.id"), nullable=True
    )
    participation_type: Mapped[str] = mapped_column(
        String, default=QuestParticipationType.OPEN, nullable=False
    )
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sponsoring_organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    xp_reward: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # When the work can be done, in the giver's words ("a qualquer hora do
    # dia", "amanhã ao amanhecer"). Informational only. None: not set.
    schedule_text: Mapped[str | None] = mapped_column(String, nullable=True)
    schedule_on_notice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # A villager's own request (app.game.quests.local_requests): who asked,
    # and the bronze they pay from their purse on completion.
    giver_npc_id: Mapped[str | None] = mapped_column(ForeignKey("npcs.id"), nullable=True)
    reward_bronze: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # Daily village request director metadata.  Null for authored quests and
    # organization contracts.
    request_template_key: Mapped[str | None] = mapped_column(String, nullable=True)
    request_generated_world_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    settlement_location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    target_location_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )


class QuestObjective(Base):
    __tablename__ = "quest_objectives"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("qobj"))
    quest_id: Mapped[str] = mapped_column(ForeignKey("quests.id"), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(default=0)
    objective_type: Mapped[str] = mapped_column(
        String, default=ObjectiveType.INVESTIGATION, nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(
        String, default=ObjectiveTriggerType.MANUAL, nullable=False
    )
    trigger_subject_id: Mapped[str | None] = mapped_column(String, nullable=True)
    optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prerequisite_objective_id: Mapped[str | None] = mapped_column(
        ForeignKey("quest_objectives.id"), nullable=True
    )
    required_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)


class CharacterQuest(Base):
    """Per-character quest progress."""

    __tablename__ = "character_quests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("cquest"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    quest_id: Mapped[str] = mapped_column(ForeignKey("quests.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default=QuestStatus.NOT_STARTED)
    deadline_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reward_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CharacterQuestObjective(Base):
    """Per-character objective completion (an objective can be shared across many characters)."""

    __tablename__ = "character_quest_objectives"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("cqobj"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    objective_id: Mapped[str] = mapped_column(ForeignKey("quest_objectives.id"), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    progress_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


class DailyRequestGeneration(Base):
    """Idempotency marker for one village director pass per world dawn."""

    __tablename__ = "daily_request_generations"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "settlement_location_id", "world_day",
            name="uq_daily_request_generation_village_day",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("reqgen"))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    settlement_location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), nullable=False)
    world_day: Mapped[int] = mapped_column(Integer, nullable=False)
    attempted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
