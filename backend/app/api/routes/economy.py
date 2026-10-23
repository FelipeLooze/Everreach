from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.character import Character
from app.game.economy.initial_content import ensure_initial_economy_for_campaign
from app.game.economy.playable import build_economy_view
from app.schemas.economy import EconomyStateResponse

router = APIRouter(prefix="/api/campaigns", tags=["economy"])


@router.get("/{campaign_id}/economy", response_model=EconomyStateResponse)
def get_economy_state(
    campaign_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")
    if character.location_id is None:
        raise HTTPException(status_code=409, detail="Inicie o mundo antes de consultar a economia")

    # One-time compatibility path for worlds started before Phase 14 became
    # playable. New campaigns already receive this content in /start.
    ensure_initial_economy_for_campaign(db, campaign_id)
    db.commit()
    return EconomyStateResponse(**build_economy_view(db, character))
