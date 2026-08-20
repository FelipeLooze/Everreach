from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService
from app.api.dependencies.llm import get_llm_service
from app.api.serializers import to_game_state_response
from app.db.database import get_db
from app.game import engine
from app.game.combat.recovery import CombatRecoveryError
from app.game.game_state import build_game_state
from app.schemas.action import ActionRequest, ActionResponse

router = APIRouter(prefix="/api/campaigns", tags=["actions"])


@router.post("/{campaign_id}/actions", response_model=ActionResponse)
def post_action(
    campaign_id: str,
    character_id: str,
    body: ActionRequest,
    db: Session = Depends(get_db),
    llm_service: LLMService = Depends(get_llm_service),
):
    try:
        result = engine.resolve_action(
            db,
            llm_service,
            campaign_id,
            character_id,
            body.text,
            technique_id=body.technique_id,
            action_key=body.action_key,
        )
    except engine.CharacterDeadError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except engine.WorldNotStartedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CombatRecoveryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    state = build_game_state(db, campaign_id, character_id)

    return ActionResponse(
        narrative=result.narrative,
        narrator_unavailable=result.narrator_unavailable,
        mechanical_summary=result.mechanical_summary,
        intent_type=result.intent_type,
        warnings=result.warnings,
        state=to_game_state_response(db, state),
    )
