from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, Field

from app.schemas.game_state import GameStateResponse
from app.schemas.character import CharacterResponse


class CampaignCreateRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    world_profile: Literal['legacy', 'world_genesis_ap1_v1', 'world_genesis_ap1_tp1_wgs1_v1', 'world_genesis_ap1_tp1_wgs1_v2', 'world_genesis_ap1_tp1_wgs2_v1', 'world_genesis_ap1_tp1_wgs2_v2', 'world_genesis_ap1_tp1_wgs2_v3', 'world_genesis_ap1_tp1_wgs2_v4', 'world_genesis_ap1_tp1_wgs2_v5', 'world_genesis_ap1_tp1_wgs3_v1'] = 'legacy'
    world_seed: int | None = Field(default=None, ge=0, le=2**63-1, strict=True)


class CampaignResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    world_profile: str | None = None

    model_config = {"from_attributes": True}


class CampaignWithCharactersResponse(CampaignResponse):
    characters: list[CharacterResponse]


class WorldStartResponse(BaseModel):
    narrative: str
    narrator_unavailable: bool
    state: GameStateResponse


class CampaignDeleteResponse(BaseModel):
    deleted: bool
