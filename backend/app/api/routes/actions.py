from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json

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
    FormationActionRequest,
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
        from app.db.models.campaign import Campaign
        campaign = db.get(Campaign, campaign_id)
        experimental = campaign is not None and campaign.world_profile in ('world_genesis_ap1_v1', 'world_genesis_ap1_tp1_wgs1_v1', 'world_genesis_ap1_tp1_wgs1_v2', 'world_genesis_ap1_tp1_wgs2_v1', 'world_genesis_ap1_tp1_wgs2_v2', 'world_genesis_ap1_tp1_wgs2_v3', 'world_genesis_ap1_tp1_wgs2_v4', 'world_genesis_ap1_tp1_wgs2_v5', 'world_genesis_ap1_tp1_wgs3_v1')
        if experimental and body.plant_action is not None:
            from app.db.models.character import Character
            from app.db.models.location import Location
            actor=db.get(Character,character_id)
            current=db.get(Location,actor.location_id) if actor and actor.location_id else None
            if current is not None and current.type == 'genesis_formation_interior':
                raise ValueError('Não há encontro vegetal externo disponível no interior desta formação.')
        if experimental and body.plant_action is None and body.formation_action is None and body.technique_id is None:
            import unicodedata
            from app.schemas.action import PlantActionRequest
            plain = unicodedata.normalize('NFKD', body.text).encode('ascii', 'ignore').decode().lower()
            if any(w in plain for w in ('planta', 'vegetacao', 'arvore', 'folhas', 'frutos', 'flores')) and any(w in plain for w in ('observ', 'olh', 'examin', 'colet', 'colh', 'retir', 'inspec')):
                # Ambiguous prose discovers real nearby targets; selection is explicit.
                body.plant_action = PlantActionRequest(kind='look')
        from app.db.models.world_vegetation import GenesisPlantAction
        plant_replay=body.plant_action is not None and db.get(GenesisPlantAction,(campaign_id,resolved_action_key)) is not None
        checkpoint = None if plant_replay else begin_action_checkpoint(
            db,
            campaign_id,
            character_id,
            resolved_action_key,
            body.text,
        )
        formation_result=None
        if body.formation_action is not None:
            from app.game.world.genesis.local_formations import inspect_current, interact_current
            formation_result=(inspect_current(db,character_id) if body.formation_action.kind=="inspect"
                              else interact_current(db,character_id))
            if formation_result is None:raise ValueError("Nenhuma formação conhecida está no local atual.")
            public={k:formation_result[k] for k in ("name","features","dimensions") if k in formation_result}
            if campaign is not None and campaign.world_profile in ('world_genesis_ap1_tp1_wgs2_v5', 'world_genesis_ap1_tp1_wgs3_v1'):
                public.update({k:formation_result[k] for k in ("identity", "known_accesses", "investigated")
                               if k in formation_result})
            if campaign is not None and campaign.world_profile == 'world_genesis_ap1_tp1_wgs3_v1' and formation_result.get('water_source'):
                public['water_source'] = formation_result['water_source']
            if formation_result.get("water"):
                water=formation_result["water"]
                public["water"]={k:water[k] for k in ("stored_litres","capacity_litres")}
            lines=[formation_result["name"],*formation_result["features"]]
            if public.get("water"):
                lines.append(f"Volume local persistido: {public['water']['stored_litres']} de {public['water']['capacity_litres']} litros.")
            if public.get('water_source') and not public['water_source']['physical_water_present']:
                lines = [formation_result['name'], 'A fissura permanece, sem água visível neste estoque local.']
            elif public.get('water_source'):
                source = public['water_source']
                lines.append(f"Fonte local: {source['available_litres']} de {source['capacity_litres']} litros disponíveis, sem fluxo confirmado.")
            if formation_result.get("interaction"):
                lines.append(formation_result["interaction"])
            formation_result=public
            prose=" ".join(lines)
            narrator_unavailable=False
            if "identity" in public:
                from app.game.world.genesis.playable import narrate_facts
                narrated, narrator_unavailable = narrate_facts(db, campaign_id, character_id, llm_service,
                    {"known_formation": public}, body.text)
                if not narrator_unavailable:
                    prose=narrated
            result=type("FormationResult",(),{"plant_result":None,"narrative":prose,
                "narrator_unavailable":narrator_unavailable,"mechanical_summary":json.dumps(public,ensure_ascii=False),
                "intent_type":"formation","warnings":[]})()
        elif body.plant_action is not None:
            from app.game.world.genesis.vegetation.actions import resolve_plant_action
            result = resolve_plant_action(db,campaign_id,character_id,body.plant_action,resolved_action_key)
            if experimental and not plant_replay:
                from app.game.world.genesis.playable import narrate_facts, observable_facts
                from app.services.event_log import log_event
                from app.core.enums import EventType
                facts = observable_facts(result.plant_result)
                facts = {'observations': facts, 'confirmed_outcome': result.mechanical_summary}
                result.narrative, result.narrator_unavailable = narrate_facts(db, campaign_id, character_id, llm_service, facts, body.text)
                log_event(db, campaign_id, EventType.STORY_EXCHANGE, actor_type='character', actor_id=character_id,
                    payload={'action_key': resolved_action_key, 'player_text': body.text, 'narrative': result.narrative,
                             'mechanical_summary': result.mechanical_summary, 'narrator_unavailable': result.narrator_unavailable})
            if getattr(result, 'plant_result', None):
                result.plant_result.pop('species_id', None)
        else:
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

    # Plant responses can initialize cosmetic item descriptions. Include those
    # writes in the checkpoint fingerprint before committing the real transfer.
    plant_state=(to_game_state_response(db,build_game_state(db,campaign_id,character_id))
        if body.plant_action is not None else None)
    if checkpoint is not None:finalize_action_checkpoint(
        db,
        checkpoint.id,
        narrative=result.narrative,
        mechanical_summary=result.mechanical_summary,
    )

    state = build_game_state(db, campaign_id, character_id) if plant_state is None else None

    return ActionResponse(
        narrative=result.narrative,
        narrator_unavailable=result.narrator_unavailable,
        mechanical_summary=result.mechanical_summary,
        intent_type=result.intent_type,
        warnings=result.warnings,
        state=plant_state if plant_state is not None else to_game_state_response(db, state),
        plant_result=getattr(result,"plant_result",None),
        formation_result=formation_result,
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
