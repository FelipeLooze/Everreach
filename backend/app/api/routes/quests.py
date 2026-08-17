from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.character import Character
from app.db.models.quest import CharacterQuestObjective, Quest, QuestObjective
from app.game.quests.service import list_character_quests
from app.schemas.quest import QuestListResponse, QuestObjectiveResponse, QuestResponse

router = APIRouter(prefix="/api/campaigns", tags=["quests"])


@router.get("/{campaign_id}/quests", response_model=QuestListResponse)
def get_quests(campaign_id: str, character_id: str, db: Session = Depends(get_db)):
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")

    links = list_character_quests(db, character_id)
    quests = []
    for cq in links:
        quest = db.get(Quest, cq.quest_id)
        if quest is None:
            continue
        objectives = db.query(QuestObjective).filter(QuestObjective.quest_id == quest.id).all()
        completed_ids = {
            c.objective_id
            for c in db.query(CharacterQuestObjective).filter(
                CharacterQuestObjective.character_id == character_id,
                CharacterQuestObjective.completed.is_(True),
            )
        }
        quests.append(
            QuestResponse(
                quest_id=quest.id, name=quest.name, description=quest.description, status=cq.status,
                objectives=[
                    QuestObjectiveResponse(id=o.id, description=o.description, completed=o.id in completed_ids)
                    for o in objectives
                ],
            )
        )
    return QuestListResponse(quests=quests)
