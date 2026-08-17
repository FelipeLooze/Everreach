from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.character import Character, CharacterAttribute
from app.db.models.skill import CharacterSkill, CharacterTechnique, Skill, Technique
from app.schemas.character import (
    AttributeResponse,
    CharacterResponse,
    CharacterSheetResponse,
    SkillResponse,
    TechniqueResponse,
)

router = APIRouter(prefix="/api/campaigns", tags=["character"])


@router.get("/{campaign_id}/character", response_model=CharacterSheetResponse)
def get_character_sheet(campaign_id: str, character_id: str, db: Session = Depends(get_db)):
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Personagem não encontrado")

    attributes = db.query(CharacterAttribute).filter(CharacterAttribute.character_id == character_id).all()

    skill_links = db.query(CharacterSkill).filter(CharacterSkill.character_id == character_id).all()
    skills = []
    for link in skill_links:
        skill = db.get(Skill, link.skill_id)
        if skill:
            skills.append(SkillResponse(name=skill.name, mastery=link.mastery))

    technique_links = db.query(CharacterTechnique).filter(CharacterTechnique.character_id == character_id).all()
    techniques = []
    for link in technique_links:
        technique = db.get(Technique, link.technique_id)
        if technique:
            techniques.append(TechniqueResponse(name=technique.name, description=technique.description))

    return CharacterSheetResponse(
        character=CharacterResponse.model_validate(character),
        attributes=[AttributeResponse(name=a.name, value=a.value) for a in attributes],
        skills=skills,
        techniques=techniques,
    )
