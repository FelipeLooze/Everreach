from pydantic import BaseModel

from app.core.enums import (
    EncumbranceTier,
    EquipmentSlot,
    ItemAccessibility,
    ItemCondition,
    ItemQuality,
)
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
    activity: str


class NearbySimulatedPlayer(BaseModel):
    id: str
    name: str
    level: int
    xp: float
    archetype: str
    risk_tolerance: str
    goal: str
    group_id: str | None


class ActiveQuestSummary(BaseModel):
    quest_id: str
    name: str
    status: str


class SystemInventoryItemSummary(BaseModel):
    item_instance_id: str
    name: str
    type: str
    quantity: int
    quality: ItemQuality
    condition: ItemCondition | None
    material_name: str | None
    equipped_slot: EquipmentSlot | None
    accessibility: ItemAccessibility
    contained_in_name: str | None


class SystemInventorySummary(BaseModel):
    items: list[SystemInventoryItemSummary]
    total_weight: float
    carrying_capacity: float
    encumbrance: EncumbranceTier


class GameStateResponse(BaseModel):
    character: CharacterResponse
    region: RegionSummary | None
    location: LocationSummary | None
    world_time: WorldTimeResponse | None
    nearby_npcs: list[NearbyNPC]
    nearby_simulated_players: list[NearbySimulatedPlayer]
    active_quests: list[ActiveQuestSummary]
    inventory: SystemInventorySummary
    opening_narrative: str | None
    opening_narrator_unavailable: bool
