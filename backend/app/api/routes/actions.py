from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService
from app.api.dependencies.llm import get_intent_llm_service, get_narrative_llm_service
from app.api.serializers import to_game_state_response
from app.db.database import get_db
from app.game import engine
from app.game.combat.recovery import CombatRecoveryError
from app.game.game_state import build_game_state
from app.core.ids import generate_id
from app.schemas.action import (
    ActionRequest,
    ActionResponse,
    ActionUndoRequest,
    ActionUndoResponse,
    ActionUndoStatusResponse,
)
from app.services.action_undo import (
    ActionUndoError,
    begin_action_checkpoint,
    checkpoint_is_current,
    finalize_action_checkpoint,
    latest_available_checkpoint,
    restore_last_action,
)

router = APIRouter(prefix="/api/campaigns", tags=["actions"])


@router.post("/{campaign_id}/actions", response_model=ActionResponse)
def post_action(
    campaign_id: str,
    character_id: str,
    body: ActionRequest,
    db: Session = Depends(get_db),
    llm_service: LLMService = Depends(get_narrative_llm_service),
    intent_llm_service: LLMService = Depends(get_intent_llm_service),
):
    resolved_action_key = body.action_key or generate_id("action")
    try:
        checkpoint = begin_action_checkpoint(
            db,
            campaign_id,
            character_id,
            resolved_action_key,
            body.text,
        )
        result = engine.resolve_action(
            db,
            llm_service,
            campaign_id,
            character_id,
            body.text,
            technique_id=body.technique_id,
            action_key=resolved_action_key,
            intent_llm_service=intent_llm_service,
        )
    except engine.CharacterDeadError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except engine.CharacterIncapacitatedError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except engine.WorldNotStartedError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CombatRecoveryError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionUndoError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    finalize_action_checkpoint(
        db,
        checkpoint.id,
        narrative=result.narrative,
        mechanical_summary=result.mechanical_summary,
    )

    state = build_game_state(db, campaign_id, character_id)

    return ActionResponse(
        narrative=result.narrative,
        narrator_unavailable=result.narrator_unavailable,
        mechanical_summary=result.mechanical_summary,
        intent_type=result.intent_type,
        warnings=result.warnings,
        state=to_game_state_response(db, state),
    )


@router.get("/{campaign_id}/actions/undo-status", response_model=ActionUndoStatusResponse)
def get_undo_status(
    campaign_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    checkpoint = latest_available_checkpoint(db, campaign_id, character_id)
    if checkpoint is None or not checkpoint_is_current(db, checkpoint):
        return ActionUndoStatusResponse(available=False)
    return ActionUndoStatusResponse(
        available=True,
        action_text=checkpoint.player_text,
        mechanical_summary=checkpoint.mechanical_summary,
    )


@router.post("/{campaign_id}/actions/undo-last", response_model=ActionUndoResponse)
def undo_last_action(
    campaign_id: str,
    character_id: str,
    body: ActionUndoRequest,
    db: Session = Depends(get_db),
):
    checkpoint = latest_available_checkpoint(db, campaign_id, character_id)
    if checkpoint is None:
        raise HTTPException(status_code=409, detail="Não existe uma ação disponível para desfazer")
    try:
        restore_last_action(db, checkpoint, reason=body.reason)
    except ActionUndoError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    state = build_game_state(db, campaign_id, character_id)
    return ActionUndoResponse(state=to_game_state_response(db, state))
