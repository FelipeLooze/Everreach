from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.schemas.game_state import GameStateResponse
from app.schemas.character import CharacterResponse


class CampaignCreateRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CampaignResponse(BaseModel):
    id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignWithCharactersResponse(CampaignResponse):
    characters: list[CharacterResponse]


class WorldStartResponse(BaseModel):
    narrative: str
    narrator_unavailable: bool
    state: GameStateResponse


class CampaignDeleteResponse(BaseModel):
    deleted: bool
