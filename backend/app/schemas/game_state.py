from pydantic import BaseModel

from app.schemas.character import CharacterResponse


class RegionSummary(BaseModel):
    id: str
    name: str | None
    description: str | None
    discovery_status: str

    model_config = {"from_attributes": True}


class LocationSummary(BaseModel):
    id: str
    name: str | None
    type: str
    description: str | None
    discovery_status: str

    model_config = {"from_attributes": True}


class WorldTimeResponse(BaseModel):
    year: int
    month: int
    day: int
    hour: int
    minute: int

    model_config = {"from_attributes": True}


class NearbyNPC(BaseModel):
    id: str
    name: str
    role: str


class NearbySimulatedPlayer(BaseModel):
    id: str
    name: str
    level: int
    archetype: str


class ActiveQuestSummary(BaseModel):
    quest_id: str
    name: str
    status: str


class GameStateResponse(BaseModel):
    character: CharacterResponse
    region: RegionSummary | None
    location: LocationSummary | None
    world_time: WorldTimeResponse | None
    nearby_npcs: list[NearbyNPC]
    nearby_simulated_players: list[NearbySimulatedPlayer]
    active_quests: list[ActiveQuestSummary]
    opening_narrative: str | None
    opening_narrator_unavailable: bool
