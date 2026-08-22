"""Phase 20B — API schema for the Player Map Data Contract (20A).

Mirrors app.game.map.view's dataclasses exactly; this file exists only
because Pydantic response_model validation needs its own schema class,
not because the contract itself differs.
"""
from pydantic import BaseModel


class MapViewRegionSchema(BaseModel):
    id: str
    name: str | None
    discovery_status: str


class MapViewLocationSchema(BaseModel):
    id: str
    region_id: str
    subregion_id: str | None
    type: str
    name: str | None
    precision: str | None
    x: int | None
    y: int | None
    discovery_status: str
    source: str
    known_aspects: list[str]


class MapViewRouteSchema(BaseModel):
    from_location_id: str
    to_location_id: str
    direction: str | None
    connection_type: str
    distance: float
    danger: int


class MapViewDataSchema(BaseModel):
    campaign_id: str
    character_id: str
    scope: str | None
    regions: list[MapViewRegionSchema]
    locations: list[MapViewLocationSchema]
    routes: list[MapViewRouteSchema]
