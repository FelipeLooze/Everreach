from pydantic import BaseModel

from app.schemas.character import (
    AttributeResponse,
    ClassDefinitionResponse,
    ClassOfferResponse,
    ProfessionResponse,
)


class CharacterXPProgressResponse(BaseModel):
    level: int
    current: float
    to_next_level: float


class ResourceProgressResponse(BaseModel):
    key: str
    name: str
    current: float
    maximum: float


class SystemProgressionResponse(BaseModel):
    character_id: str
    character_name: str
    character_xp: CharacterXPProgressResponse
    professions: list[ProfessionResponse]
    active_class: ClassDefinitionResponse | None
    class_offers: list[ClassOfferResponse]
    attributes: list[AttributeResponse]
    resources: list[ResourceProgressResponse]
