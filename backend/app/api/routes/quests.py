from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.enums import QuestStatus
from app.db.database import get_db
from app.db.models.character import Character
from app.db.models.quest import CharacterQuest, CharacterQuestObjective, Quest, QuestObjective
from app.db.models.region import Region
from app.game.quests.discovery import is_quest_known_to_character
from app.game.schedules import player_knows_quest_schedule
from app.game.quests.service import (
    QuestLifecycleError,
    abandon_known_quest,
    accept_known_quest,
)
from app.schemas.quest import QuestListResponse, QuestObjectiveResponse, QuestResponse

router = APIRouter(prefix="/api/campaigns", tags=["quests"])


def _require_character(db: Session, campaign_id: str, character_id: str) -> Character:
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")
    return character


def _quest_response(
    db: Session,
    character_id: str,
    quest: Quest,
    participation: CharacterQuest | None,
) -> QuestResponse:
    objectives = (
        db.query(QuestObjective)
        .filter(QuestObjective.quest_id == quest.id)
        .order_by(QuestObjective.order, QuestObjective.id)
        .all()
    )
    progress_by_id = {
        row.objective_id: row
        for row in db.query(CharacterQuestObjective)
        .filter(
            CharacterQuestObjective.character_id == character_id,
        )
        .all()
    }
    return QuestResponse(
        quest_id=quest.id,
        name=quest.name,
        description=quest.description,
        status=participation.status if participation is not None else quest.status,
        schedule=(
            None if not quest.schedule_text
            else quest.schedule_text
            if player_knows_quest_schedule(db, db.get(Character, character_id).campaign_id, character_id, quest)
            else "desconhecido"
        ),
        objectives=[
            QuestObjectiveResponse(
                id=objective.id,
                description=objective.description,
                completed=(
                    objective.id in progress_by_id
                    and progress_by_id[objective.id].completed
                ),
                progress_count=(
                    progress_by_id[objective.id].progress_count
                    if objective.id in progress_by_id else 0
                ),
                required_count=objective.required_count,
            )
            for objective in objectives
        ],
    )


@router.get("/{campaign_id}/quests", response_model=QuestListResponse)
def get_quests(campaign_id: str, character_id: str, db: Session = Depends(get_db)):
    _require_character(db, campaign_id, character_id)
    participation_by_quest = {
        row.quest_id: row
        for row in db.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character_id)
        .all()
    }
    campaign_quests = (
        db.query(Quest)
        .join(Region, Region.id == Quest.region_id)
        .filter(Region.campaign_id == campaign_id)
        .all()
    )
    visible = [
        quest
        for quest in campaign_quests
        if quest.id in participation_by_quest
        or is_quest_known_to_character(db, campaign_id, character_id, quest.id)
    ]
    status_order = {
        QuestStatus.ACTIVE: 0,
        QuestStatus.AVAILABLE: 1,
        QuestStatus.COMPLETED: 2,
        QuestStatus.FAILED: 3,
        QuestStatus.CANCELLED: 4,
        QuestStatus.EXPIRED: 5,
        QuestStatus.RESOLVED_EXTERNALLY: 6,
    }
    visible.sort(
        key=lambda quest: (
            status_order.get(
                participation_by_quest.get(quest.id).status
                if quest.id in participation_by_quest
                else quest.status,
                99,
            ),
            quest.name,
        )
    )
    return QuestListResponse(
        quests=[
            _quest_response(db, character_id, quest, participation_by_quest.get(quest.id))
            for quest in visible
        ]
    )


@router.post("/{campaign_id}/quests/{quest_id}/accept", response_model=QuestResponse)
def accept_quest_route(
    campaign_id: str,
    quest_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    _require_character(db, campaign_id, character_id)
    try:
        participation = accept_known_quest(db, campaign_id, character_id, quest_id)
    except QuestLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    quest = db.get(Quest, quest_id)
    db.commit()
    return _quest_response(db, character_id, quest, participation)


@router.post("/{campaign_id}/quests/{quest_id}/abandon", response_model=QuestResponse)
def abandon_quest_route(
    campaign_id: str,
    quest_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    _require_character(db, campaign_id, character_id)
    try:
        participation = abandon_known_quest(db, campaign_id, character_id, quest_id)
    except QuestLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    quest = db.get(Quest, quest_id)
    db.commit()
    return _quest_response(db, character_id, quest, participation)
