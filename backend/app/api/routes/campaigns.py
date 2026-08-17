from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai import context_builder, narrator
from app.ai.llm_service import LLMService, LLMServiceError
from app.api.dependencies.llm import get_llm_service
from app.db.database import get_db
from app.db.models.campaign import Campaign
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.region import Region
from app.game.character.service import create_character
from app.game.world.seed import create_campaign, grant_initial_player_knowledge, seed_initial_region
from app.game.world.reset import delete_campaign
from app.services.event_log import log_event
from app.core.enums import EventType, DiscoveryStatus
from app.api.serializers import to_game_state_response
from app.game.game_state import build_game_state
from app.schemas.campaign import (
    CampaignCreateRequest,
    CampaignDeleteResponse,
    CampaignResponse,
    CampaignWithCharactersResponse,
    WorldStartResponse,
)
from app.schemas.character import CharacterCreateRequest, CharacterResponse
from app.game.discovery.service import set_location_discovery

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignWithCharactersResponse])
def list_campaigns(db: Session = Depends(get_db)):
    """List persisted campaigns and their protagonists for the continue screen."""
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc(), Campaign.id.desc()).all()
    if not campaigns:
        return []

    campaign_ids = [campaign.id for campaign in campaigns]
    characters = (
        db.query(Character)
        .filter(Character.campaign_id.in_(campaign_ids))
        .order_by(Character.created_at.asc(), Character.id.asc())
        .all()
    )
    characters_by_campaign: dict[str, list[Character]] = {
        campaign_id: [] for campaign_id in campaign_ids
    }
    for character in characters:
        characters_by_campaign[character.campaign_id].append(character)

    return [
        CampaignWithCharactersResponse(
            id=campaign.id,
            name=campaign.name,
            created_at=campaign.created_at,
            characters=characters_by_campaign[campaign.id],
        )
        for campaign in campaigns
    ]


@router.post("", response_model=CampaignResponse)
def create_campaign_route(body: CampaignCreateRequest, db: Session = Depends(get_db)) -> Campaign:
    campaign = create_campaign(db, body.name)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return campaign


@router.delete("/{campaign_id}", response_model=CampaignDeleteResponse)
def delete_campaign_route(campaign_id: str, db: Session = Depends(get_db)):
    if not delete_campaign(db, campaign_id):
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    db.commit()
    return CampaignDeleteResponse(deleted=True)


@router.post("/{campaign_id}/characters", response_model=CharacterResponse)
def create_character_route(
    campaign_id: str,
    body: CharacterCreateRequest,
    db: Session = Depends(get_db),
):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    character = create_character(
        db,
        campaign_id,
        body.name,
        None,
        None,
    )

    db.commit()
    db.refresh(character)
    return character


@router.post("/{campaign_id}/start", response_model=WorldStartResponse)
def start_world(
    campaign_id: str,
    character_id: str,
    db: Session = Depends(get_db),
    llm_service: LLMService = Depends(get_llm_service),
):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")

    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado nesta campanha")

    region = db.query(Region).filter(Region.campaign_id == campaign_id).first()
    if region is None:
        region, village = seed_initial_region(db, campaign_id)
    else:
        village = db.query(Location).filter(Location.region_id == region.id, Location.type == "village").first()
        if village is None:
            raise HTTPException(status_code=500, detail="A campanha não possui uma localização inicial")

    character.region_id = region.id
    character.location_id = village.id
    set_location_discovery(
        db,
        character.id,
        village.id,
        DiscoveryStatus.VISITED,
    )
    grant_initial_player_knowledge(
        db,
        campaign_id,
        character.id,
    )

    db.commit()
    state = build_game_state(db, campaign_id, character_id)
    if state.opening_narrative:
        return WorldStartResponse(
            narrative=state.opening_narrative,
            narrator_unavailable=state.opening_narrator_unavailable,
            state=to_game_state_response(state),
        )

    nearby_names = ", ".join(
        player.name for player in state.nearby_simulated_players
    )

    mechanical_intro = (
        f"Este é o primeiro instante narrado de {character.name} após um transporte "
        f"involuntário de seu mundo de origem para outro mundo. "
        f"Esta campanha começa durante a Primeira Chegada: uma ocorrência massiva na qual "
        f"muitas pessoas foram transportadas fisicamente quase ao mesmo tempo. "
        f"{character.name} está de pé em uma praça como resultado direto do transporte e "
        f"ainda não realizou nenhuma ação voluntária. "

        f"A localização canônica de backend é {village.name}, na região {region.name}. "
        f"Esses nomes NÃO devem ser revelados ao protagonista apenas por aparecerem neste "
        f"resumo; só podem ser usados como conhecimento do protagonista se PLAYER KNOWLEDGE "
        f"ou outro fato autorizado permitir. "

        f"Há outras pessoas transportadas nas proximidades. Identidades persistentes presentes "
        f"no backend: {nearby_names or 'nenhuma'}. Os nomes dessas pessoas também não são "
        f"automaticamente conhecidos pelo protagonista. Além delas, uma multidão anônima de "
        f"recém-chegados pode compor o fundo da Primeira Chegada. "

        f"Os habitantes nativos presentes testemunham o fenômeno, mas não recebem conhecimento "
        f"automático sobre sua causa. "

        f"Não descreva esta chegada como jogo, login, logout, servidor, VR, VRMMORPG, "
        f"sincronização de jogo ou lançamento. "
        f"Não invente mensagens da Interface ou do Sistema. "
        f"A narrativa deve terminar antes da primeira ação voluntária do protagonista."
    )
    narrator_unavailable = False
    try:
        narrative = narrator.narrate(
            llm_service,
            mechanical_intro,
            context_builder.build_context(db, state),
            player_input="(nenhuma ação do jogador; abertura da campanha)",
            recent_history="(nenhum histórico; este é o primeiro instante)",
            mode="OPENING",
        )
    except LLMServiceError:
        narrative = (
            "As vozes chegam antes que a visão se firme. Gritos, perguntas e passos se misturam "
            "em uma confusão crescente. Quando o mundo se torna nítido, há pedra sob os pés e "
            "uma praça desconhecida tomada por pessoas que parecem ter chegado no mesmo instante. "
            "Nas margens, habitantes locais observam o acontecimento. Nenhuma explicação acompanha a chegada."
        )
        narrator_unavailable = True

    log_event(
        db,
        campaign_id,
        EventType.WORLD_STARTED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "narrative": narrative,
            "narrator_unavailable": narrator_unavailable,
            "arrival_kind": "FIRST_ARRIVAL",
        },
    )
    db.commit()
    state = build_game_state(db, campaign_id, character_id)

    return WorldStartResponse(
        narrative=narrative,
        narrator_unavailable=narrator_unavailable,
        state=to_game_state_response(state),
    )
