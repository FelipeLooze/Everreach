from sqlalchemy.orm import Session

from app.core.enums import EventType, QuestStatus
from app.db.models.quest import (
    CharacterQuest,
    CharacterQuestObjective,
    Quest,
    QuestObjective,
)
from app.db.models.character import Character
from app.services.event_log import log_event


def start_quest(db: Session, character_id: str, quest_id: str) -> CharacterQuest:
    existing = (
        db.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character_id, CharacterQuest.quest_id == quest_id)
        .first()
    )
    if existing:
        return existing

    cq = CharacterQuest(character_id=character_id, quest_id=quest_id, status=QuestStatus.ACTIVE)
    db.add(cq)
    db.flush()
    character = db.get(Character, character_id)
    if character is not None:
        log_event(
            db,
            character.campaign_id,
            EventType.QUEST_STARTED,
            actor_type="character",
            actor_id=character_id,
            payload={"quest_id": quest_id},
        )
    return cq


def complete_objective(db: Session, campaign_id: str, character_id: str, objective_id: str) -> CharacterQuestObjective:
    entry = (
        db.query(CharacterQuestObjective)
        .filter(
            CharacterQuestObjective.character_id == character_id,
            CharacterQuestObjective.objective_id == objective_id,
        )
        .first()
    )
    if not entry:
        entry = CharacterQuestObjective(character_id=character_id, objective_id=objective_id, completed=True)
        db.add(entry)
    else:
        entry.completed = True
    db.flush()

    log_event(
        db,
        campaign_id,
        EventType.QUEST_OBJECTIVE_COMPLETED,
        actor_type="character",
        actor_id=character_id,
        payload={"objective_id": objective_id},
    )

    objective = db.get(QuestObjective, objective_id)
    if objective:
        remaining = (
            db.query(QuestObjective)
            .filter(QuestObjective.quest_id == objective.quest_id)
            .all()
        )
        completed_ids = {
            c.objective_id
            for c in db.query(CharacterQuestObjective).filter(
                CharacterQuestObjective.character_id == character_id, CharacterQuestObjective.completed.is_(True)
            )
        }
        if all(o.id in completed_ids for o in remaining):
            cq = (
                db.query(CharacterQuest)
                .filter(CharacterQuest.character_id == character_id, CharacterQuest.quest_id == objective.quest_id)
                .first()
            )
            if cq and cq.status != QuestStatus.COMPLETED:
                cq.status = QuestStatus.COMPLETED
                log_event(
                    db,
                    campaign_id,
                    EventType.QUEST_COMPLETED,
                    actor_type="character",
                    actor_id=character_id,
                    payload={"quest_id": objective.quest_id},
                )

    return entry


def list_character_quests(db: Session, character_id: str) -> list[CharacterQuest]:
    return db.query(CharacterQuest).filter(CharacterQuest.character_id == character_id).all()
