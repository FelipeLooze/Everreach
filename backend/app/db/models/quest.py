from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ObjectiveTriggerType, ObjectiveType, QuestSource, QuestStatus
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


class CharacterQuest(Base):
    """Per-character quest progress."""

    __tablename__ = "character_quests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("cquest"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    quest_id: Mapped[str] = mapped_column(ForeignKey("quests.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default=QuestStatus.NOT_STARTED)
    deadline_world_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CharacterQuestObjective(Base):
    """Per-character objective completion (an objective can be shared across many characters)."""

    __tablename__ = "character_quest_objectives"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: generate_id("cqobj"))
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    objective_id: Mapped[str] = mapped_column(ForeignKey("quest_objectives.id"), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
