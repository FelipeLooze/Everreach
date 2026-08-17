from typing import Annotated

from pydantic import BaseModel, StringConstraints


class CharacterCreateRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CharacterResponse(BaseModel):
    id: str
    name: str
    level: int
    xp: float
    hp_current: float
    hp_max: float
    mana_current: float
    mana_max: float
    stamina_current: float
    stamina_max: float
    status: str
    region_id: str | None
    location_id: str | None

    model_config = {"from_attributes": True}


class AttributeResponse(BaseModel):
    name: str
    value: int


class SkillResponse(BaseModel):
    name: str
    mastery: float


class TechniqueResponse(BaseModel):
    name: str
    description: str


class CharacterSheetResponse(BaseModel):
    character: CharacterResponse
    attributes: list[AttributeResponse]
    skills: list[SkillResponse]
    techniques: list[TechniqueResponse]
