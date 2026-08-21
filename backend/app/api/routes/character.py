from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.character import Character
from app.db.models.character_class import CharacterClassOffer
from app.db.models.skill import CharacterSkill, Skill
from app.schemas.character import (
    AttributeResponse,
    CharacterResponse,
    CharacterSheetResponse,
    ClassDefinitionResponse,
    ClassOfferResponse,
    ProfessionResponse,
    SkillResponse,
    TechniqueResponse,
)
from app.game.professions.service import list_character_professions
from app.game.attributes.service import list_character_attributes
from app.game.classes.service import (
    ClassChoiceError,
    accept_class_offer,
    delay_class_offer,
    get_active_class,
    list_visible_class_offers,
)
from app.game.progression.context import build_system_progression_context
from app.game.skills.techniques import list_character_techniques
from app.schemas.progression import (
    CharacterXPProgressResponse,
    ResourceProgressResponse,
    SystemProgressionResponse,
)

router = APIRouter(prefix="/api/campaigns", tags=["character"])


def _class_response(class_definition) -> ClassDefinitionResponse:
    return ClassDefinitionResponse(
        id=class_definition.id,
        name=class_definition.name,
        description=class_definition.description,
    )


def _offer_response(offer: CharacterClassOffer) -> ClassOfferResponse:
    return ClassOfferResponse(
        id=offer.id,
        status=offer.status,
        class_definition=_class_response(offer.class_definition),
    )


def _character_and_offer(
    db: Session,
    campaign_id: str,
    character_id: str,
    offer_id: str,
) -> tuple[Character, CharacterClassOffer]:
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado")
    offer = db.get(CharacterClassOffer, offer_id)
    if offer is None or offer.character_id != character.id:
        raise HTTPException(status_code=404, detail="Oferta de classe não encontrada")
    return character, offer


@router.get(
    "/{campaign_id}/character/progression",
    response_model=SystemProgressionResponse,
)
def get_system_progression(
    campaign_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    try:
        context = build_system_progression_context(
            db,
            campaign_id,
            character_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Personagem não encontrado") from exc
    character = context.character
    return SystemProgressionResponse(
        character_id=character.id,
        character_name=character.name,
        character_xp=CharacterXPProgressResponse(
            level=character.level,
            current=round(character.xp, 1),
            to_next_level=round(context.xp_to_next_level, 1),
        ),
        professions=[
            ProfessionResponse(
                key=link.profession.key,
                name=link.profession.name,
                level=link.level,
                xp=round(link.xp, 1),
            )
            for link in context.professions
        ],
        active_class=(
            _class_response(context.active_class)
            if context.active_class is not None
            else None
        ),
        class_offers=[_offer_response(offer) for offer in context.class_offers],
        attributes=[
            AttributeResponse(
                key=attribute.key,
                name=attribute.definition.name,
                value=attribute.value,
            )
            for attribute in context.attributes
        ],
        resources=[
            ResourceProgressResponse(
                key="HP",
                name="Vida",
                current=round(character.hp_current, 1),
                maximum=round(character.hp_max, 1),
            ),
            ResourceProgressResponse(
                key="MANA",
                name="Mana",
                current=round(character.mana_current, 1),
                maximum=round(character.mana_max, 1),
            ),
            ResourceProgressResponse(
                key="STAMINA",
                name="Fôlego",
                current=round(character.stamina_current, 1),
                maximum=round(character.stamina_max, 1),
            ),
        ],
    )


@router.get("/{campaign_id}/character", response_model=CharacterSheetResponse)
def get_character_sheet(campaign_id: str, character_id: str, db: Session = Depends(get_db)):
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado")

    attributes = list_character_attributes(db, character_id)

    skill_links = db.query(CharacterSkill).filter(CharacterSkill.character_id == character_id).all()
    skills = []
    for link in skill_links:
        skill = db.get(Skill, link.skill_id)
        if skill:
            skills.append(SkillResponse(name=skill.name, mastery=link.mastery))

    techniques = [
        TechniqueResponse(
            id=technique.id,
            name=technique.name,
            description=technique.description,
            type=technique.technique_type,
        )
        for technique in list_character_techniques(db, character_id)
    ]

    professions = [
        ProfessionResponse(
            key=link.profession.key,
            name=link.profession.name,
            level=link.level,
            xp=link.xp,
        )
        for link in list_character_professions(db, character_id)
    ]
    active_class = get_active_class(db, character)
    class_offers = list_visible_class_offers(db, character.id)

    return CharacterSheetResponse(
        character=CharacterResponse.model_validate(character),
        attributes=[
            AttributeResponse(
                key=a.key,
                name=a.definition.name,
                value=a.value,
            )
            for a in attributes
        ],
        professions=professions,
        active_class=(
            _class_response(active_class) if active_class is not None else None
        ),
        class_offers=[_offer_response(offer) for offer in class_offers],
        skills=skills,
        techniques=techniques,
    )


@router.post(
    "/{campaign_id}/character/class-offers/{offer_id}/accept",
    response_model=ClassDefinitionResponse,
)
def accept_character_class_offer(
    campaign_id: str,
    offer_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    character, offer = _character_and_offer(
        db,
        campaign_id,
        character_id,
        offer_id,
    )
    try:
        class_definition = accept_class_offer(
            db,
            campaign_id,
            character,
            offer,
        )
    except ClassChoiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _class_response(class_definition)


@router.post(
    "/{campaign_id}/character/class-offers/{offer_id}/delay",
    response_model=ClassOfferResponse,
)
def delay_character_class_offer(
    campaign_id: str,
    offer_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    character, offer = _character_and_offer(
        db,
        campaign_id,
        character_id,
        offer_id,
    )
    try:
        delayed = delay_class_offer(
            db,
            campaign_id,
            character,
            offer,
        )
    except ClassChoiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _offer_response(delayed)
