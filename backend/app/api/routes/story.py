import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai import context_builder, narrator
from app.ai.llm_service import LLMService, LLMServiceError
from app.api.dependencies.llm import get_regeneration_llm_service
from app.core.config import get_settings
from app.core.enums import EventType
from app.db.database import get_db
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.game.game_state import build_game_state
from app.schemas.story import (
    StoryEntryResponse,
    StoryLogResponse,
    StoryRegenerationRequest,
    StoryRegenerationResponse,
)
from app.services.event_log import log_event
from app.services.story_log import get_story_log
from app.services.action_undo import (
    checkpoint_is_current,
    latest_available_checkpoint,
    refresh_checkpoint_after_cosmetic_change,
)

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


@router.post("/{campaign_id}/story/regenerate", response_model=StoryRegenerationResponse)
def regenerate_last_narrative(
    campaign_id: str,
    character_id: str,
    body: StoryRegenerationRequest,
    db: Session = Depends(get_db),
    llm_service: LLMService = Depends(get_regeneration_llm_service),
):
    """Rewrite only the latest narrator message; never replay game mechanics."""
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")

    source_events = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.actor_id == character_id,
            WorldEvent.event_type.in_((EventType.WORLD_STARTED, EventType.STORY_EXCHANGE)),
        )
        .order_by(WorldEvent.created_at.desc(), WorldEvent.id.desc())
        .all()
    )
    source_event = None
    source_payload: dict = {}
    for candidate in source_events:
        try:
            candidate_payload = json.loads(candidate.payload_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if candidate_payload.get("narrative"):
            source_event = candidate
            source_payload = candidate_payload
            break
    if source_event is None:
        raise HTTPException(status_code=409, detail="Ainda não existe uma mensagem para regenerar")

    story = get_story_log(db, campaign_id, character_id)
    target_entry_id = f"{source_event.id}:narrator"
    previous_entry = next((entry for entry in story if entry.id == target_entry_id), None)
    if previous_entry is None:
        raise HTTPException(status_code=409, detail="A última mensagem não pôde ser reconstruída")

    state = build_game_state(db, campaign_id, character_id)
    player_input = source_payload.get("player_text") or "(abertura da campanha; nenhuma ação do jogador)"
    mode = "OPENING" if source_event.event_type == EventType.WORLD_STARTED else "CONTINUATION"
    history_without_target = [
        entry for entry in story if not entry.id.startswith(f"{source_event.id}:")
    ]
    recent_history = context_builder.build_recent_history(history_without_target[-8:])
    scene_context = context_builder.build_context(
        db,
        state,
        active_interlocutor=source_payload.get("npc_id"),
        player_input=player_input,
    )
    mechanical_summary = source_payload.get("mechanical_summary") or (
        "Reescreva apenas a apresentação textual deste mesmo momento. "
        "Nenhum novo resultado mecânico foi autorizado."
    )

    settings = get_settings()
    try:
        regenerated = narrator.narrate(
            llm_service,
            mechanical_summary,
            scene_context,
            player_input=player_input,
            recent_history=recent_history,
            mode=mode,
            previous_narrative=previous_entry.text,
            revision_feedback=body.feedback,
            enforce_player_agency=settings.narrative_player_agency_guard_enabled,
            automatic_validation=settings.narrative_automatic_validation_enabled,
        )
    except LLMServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail="A regeneração por IA está desativada ou indisponível",
        ) from exc

    compatible_checkpoint = latest_available_checkpoint(db, campaign_id, character_id)
    if compatible_checkpoint is not None and not checkpoint_is_current(db, compatible_checkpoint):
        compatible_checkpoint = None
    log_event(
        db,
        campaign_id,
        EventType.STORY_REGENERATED,
        actor_type="character",
        actor_id=character_id,
        payload={
            "target_event_id": source_event.id,
            "narrative": regenerated,
            "feedback": body.feedback,
        },
    )
    refresh_checkpoint_after_cosmetic_change(db, compatible_checkpoint)
    db.commit()

    effective_entry = next(
        entry for entry in get_story_log(db, campaign_id, character_id) if entry.id == target_entry_id
    )
    return StoryRegenerationResponse(
        entry=StoryEntryResponse(
            id=effective_entry.id,
            kind=effective_entry.kind,
            text=effective_entry.text,
            created_at=effective_entry.created_at,
        )
    )
