from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.core.enums import EarthProfession


class CharacterCreateRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    earth_profession: EarthProfession | None = None


class CharacterResponse(BaseModel):
    id: str
    name: str
    background: str | None
    profession_affinity_key: str | None
    active_class_id: str | None
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
    key: str
    name: str
    value: int


class SkillResponse(BaseModel):
    name: str
    mastery: float


class ProfessionResponse(BaseModel):
    key: str
    name: str
    level: int
    xp: float


class ClassDefinitionResponse(BaseModel):
    id: str
    name: str
    description: str


class ClassOfferResponse(BaseModel):
    id: str
    status: str
    class_definition: ClassDefinitionResponse


class TechniqueResponse(BaseModel):
    id: str
    name: str
    description: str
    type: str


class CharacterSheetResponse(BaseModel):
    character: CharacterResponse
    attributes: list[AttributeResponse]
    professions: list[ProfessionResponse]
    active_class: ClassDefinitionResponse | None
    class_offers: list[ClassOfferResponse]
    skills: list[SkillResponse]
    techniques: list[TechniqueResponse]
