from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.character import Character
from app.schemas.story import StoryEntryResponse, StoryLogResponse
from app.services.story_log import get_story_log

router = APIRouter(prefix="/api/campaigns", tags=["story"])


@router.get("/{campaign_id}/story", response_model=StoryLogResponse)
def get_story(campaign_id: str, character_id: str, db: Session = Depends(get_db)):
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")

    entries = get_story_log(db, campaign_id, character_id)
    return StoryLogResponse(
        entries=[
            StoryEntryResponse(id=entry.id, kind=entry.kind, text=entry.text, created_at=entry.created_at)
            for entry in entries
        ]
    )
