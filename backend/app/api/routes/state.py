from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.serializers import to_game_state_response
from app.db.database import get_db
from app.game.game_state import build_game_state
from app.schemas.game_state import GameStateResponse

router = APIRouter(prefix="/api/campaigns", tags=["state"])


@router.get("/{campaign_id}/state", response_model=GameStateResponse)
def get_state(campaign_id: str, character_id: str, db: Session = Depends(get_db)):
    try:
        state = build_game_state(db, campaign_id, character_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_game_state_response(db, state)
